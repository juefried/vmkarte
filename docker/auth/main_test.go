package main

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"golang.org/x/crypto/bcrypt"
)

func testServer(t *testing.T) (*server, string) {
	t.Helper()

	hash, err := bcrypt.GenerateFromPassword([]byte("secret"), bcrypt.MinCost)
	if err != nil {
		t.Fatal(err)
	}

	path := filepath.Join(t.TempDir(), ".htpasswd")
	if err := os.WriteFile(path, []byte("vmkarte:"+string(hash)+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	cfg := config{
		passwordFile: path,
		cookieName:   "vmkarte_session",
		cookieSecure: true,
		cookieMaxAge: 90 * 24 * time.Hour,
	}

	srv, err := newServer(cfg, []byte("01234567890123456789012345678901"))
	if err != nil {
		t.Fatal(err)
	}
	srv.now = func() time.Time { return time.Unix(1_800_000_000, 0) }
	return srv, path
}

func TestSignAndVerifyToken(t *testing.T) {
	key := []byte("01234567890123456789012345678901")
	now := time.Unix(1_800_000_000, 0)

	token := signToken(key, now.Add(time.Hour), []byte("abcdefghijklmnopqrstuvwxyz123456"))
	if !verifyToken(key, token, now) {
		t.Fatal("valid token was rejected")
	}
	if verifyToken(key, token, now.Add(2*time.Hour)) {
		t.Fatal("expired token was accepted")
	}
	if verifyToken([]byte("another-key-that-is-long-enough-1234"), token, now) {
		t.Fatal("token with wrong key was accepted")
	}
	if verifyToken(key, token+"x", now) {
		t.Fatal("tampered token was accepted")
	}
	if verifyToken(key, "v1.bad", now) {
		t.Fatal("malformed token was accepted")
	}
}

func TestReadCredentialsNormalizesBcryptPrefix(t *testing.T) {
	hash, err := bcrypt.GenerateFromPassword([]byte("secret"), bcrypt.MinCost)
	if err != nil {
		t.Fatal(err)
	}
	legacy := string(hash)
	legacy = strings.Replace(legacy, "$2a$", "$2y$", 1)
	legacy = strings.Replace(legacy, "$2b$", "$2y$", 1)
	path := filepath.Join(t.TempDir(), ".htpasswd")
	if err := os.WriteFile(path, []byte("vmkarte:"+legacy+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	got, found, err := readCredentials(path, "vmkarte")
	if err != nil {
		t.Fatal(err)
	}
	if !found {
		t.Fatal("user not found")
	}
	if err := bcrypt.CompareHashAndPassword(got, []byte("secret")); err != nil {
		t.Fatalf("normalized hash did not verify: %v", err)
	}
}

func TestReadCredentialsPrefersBcryptOverLegacy(t *testing.T) {
	hash, err := bcrypt.GenerateFromPassword([]byte("secret"), bcrypt.MinCost)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), ".htpasswd")
	content := "vmkarte:$apr1$legacy$not-used\n" +
		"vmkarte:" + string(hash) + "\n"
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}

	got, found, err := readCredentials(path, "vmkarte")
	if err != nil {
		t.Fatal(err)
	}
	if !found {
		t.Fatal("user not found")
	}
	if err := bcrypt.CompareHashAndPassword(got, []byte("secret")); err != nil {
		t.Fatalf("bcrypt hash was not preferred: %v", err)
	}
}

func TestSanitizeNext(t *testing.T) {
	cases := map[string]string{
		"":                     "/",
		"/":                    "/",
		"/karte.html":          "/karte.html",
		"/?tag=test":           "/?tag=test",
		"https://evil.test/":   "/",
		"//evil.test/":         "/",
		"\\\\evil.test\\path":  "/",
		"/login":               "/",
		"/login?next=/":        "/",
		"/logout":              "/",
		"/ok\r\nInjected: yes": "/",
	}
	for input, want := range cases {
		if got := sanitizeNext(input, "/"); got != want {
			t.Errorf("sanitizeNext(%q) = %q, want %q", input, got, want)
		}
	}
}

func TestLoginSuccessSetsCookie(t *testing.T) {
	srv, _ := testServer(t)

	form := url.Values{
		"username": {"vmkarte"},
		"password": {"secret"},
		"next":     {"/karte.html"},
	}
	req := httptest.NewRequest(http.MethodPost, "/login", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	rec := httptest.NewRecorder()

	srv.login(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusSeeOther)
	}
	if location := rec.Header().Get("Location"); location != "/karte.html" {
		t.Fatalf("Location = %q", location)
	}
	cookies := rec.Result().Cookies()
	if len(cookies) != 1 {
		t.Fatalf("got %d cookies, want 1", len(cookies))
	}
	cookie := cookies[0]
	if cookie.Name != "vmkarte_session" {
		t.Errorf("cookie name = %q", cookie.Name)
	}
	if !cookie.HttpOnly || !cookie.Secure {
		t.Errorf("cookie is missing HttpOnly or Secure")
	}
	if cookie.SameSite != http.SameSiteLaxMode {
		t.Errorf("SameSite = %v", cookie.SameSite)
	}
	if cookie.MaxAge <= 0 {
		t.Errorf("MaxAge = %d", cookie.MaxAge)
	}
	if !verifyToken(srv.key, cookie.Value, srv.now()) {
		t.Errorf("cookie token is invalid")
	}
}

func TestLoginFailureDoesNotSetCookie(t *testing.T) {
	srv, _ := testServer(t)

	form := url.Values{
		"username": {"vmkarte"},
		"password": {"wrong"},
	}
	req := httptest.NewRequest(http.MethodPost, "/login", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	rec := httptest.NewRecorder()

	srv.login(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusUnauthorized)
	}
	if len(rec.Result().Cookies()) != 0 {
		t.Fatal("failed login set a cookie")
	}
	if !strings.Contains(rec.Body.String(), "Anmeldung nicht möglich") {
		t.Fatal("generic error message missing")
	}
}

func TestLoginRejectsCrossSiteOrigin(t *testing.T) {
	srv, _ := testServer(t)

	form := url.Values{
		"username": {"vmkarte"},
		"password": {"secret"},
	}
	req := httptest.NewRequest(http.MethodPost, "/login", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Origin", "https://evil.test")
	rec := httptest.NewRecorder()

	srv.login(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusForbidden)
	}
}

func TestSessionCheck(t *testing.T) {
	srv, _ := testServer(t)
	expires := srv.now().Add(time.Hour)
	token := signToken(srv.key, expires, []byte("abcdefghijklmnopqrstuvwxyz123456"))

	valid := httptest.NewRequest(http.MethodGet, "/session-check", nil)
	valid.AddCookie(&http.Cookie{Name: "vmkarte_session", Value: token})
	validRec := httptest.NewRecorder()
	srv.sessionCheck(validRec, valid)
	if validRec.Code != http.StatusNoContent {
		t.Fatalf("valid session status = %d, want %d", validRec.Code, http.StatusNoContent)
	}

	expiredToken := signToken(srv.key, srv.now().Add(-time.Hour), []byte("abcdefghijklmnopqrstuvwxyz123456"))
	expired := httptest.NewRequest(http.MethodGet, "/session-check", nil)
	expired.AddCookie(&http.Cookie{Name: "vmkarte_session", Value: expiredToken})
	expiredRec := httptest.NewRecorder()
	srv.sessionCheck(expiredRec, expired)
	if expiredRec.Code != http.StatusUnauthorized {
		t.Fatalf("expired session status = %d, want %d", expiredRec.Code, http.StatusUnauthorized)
	}
}

func TestLogoutClearsCookie(t *testing.T) {
	srv, _ := testServer(t)

	req := httptest.NewRequest(http.MethodPost, "/logout", nil)
	rec := httptest.NewRecorder()
	srv.logout(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusSeeOther)
	}
	cookies := rec.Result().Cookies()
	if len(cookies) != 1 || cookies[0].MaxAge >= 0 {
		t.Fatal("logout did not clear the session cookie")
	}
}

func TestLogoutGETClearsCookie(t *testing.T) {
	srv, _ := testServer(t)

	req := httptest.NewRequest(http.MethodGet, "/logout", nil)
	rec := httptest.NewRecorder()
	srv.logout(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusSeeOther)
	}
	if location := rec.Header().Get("Location"); location != "/login" {
		t.Fatalf("Location = %q", location)
	}
	cookies := rec.Result().Cookies()
	if len(cookies) != 1 || cookies[0].MaxAge >= 0 {
		t.Fatal("GET logout did not clear the session cookie")
	}
}

func TestHealth(t *testing.T) {
	srv, _ := testServer(t)
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	srv.health(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
}

func TestLoginBackgroundIsServed(t *testing.T) {
	srv, _ := testServer(t)

	req := httptest.NewRequest(http.MethodGet, "/login-background.jpg", nil)
	rec := httptest.NewRecorder()
	srv.loginBackground(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if got := rec.Header().Get("Content-Type"); got != "image/jpeg" {
		t.Fatalf("Content-Type = %q", got)
	}
	if rec.Body.Len() == 0 {
		t.Fatal("background image is empty")
	}
	if got := rec.Header().Get("Cache-Control"); !strings.Contains(got, "max-age") {
		t.Fatalf("Cache-Control = %q", got)
	}
}

func TestLoginBackgroundRejectsOtherMethods(t *testing.T) {
	srv, _ := testServer(t)

	req := httptest.NewRequest(http.MethodPost, "/login-background.jpg", nil)
	rec := httptest.NewRecorder()
	srv.loginBackground(rec, req)

	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusMethodNotAllowed)
	}
}

func TestLoginPageUsesBackground(t *testing.T) {
	srv, _ := testServer(t)

	req := httptest.NewRequest(http.MethodGet, "/login", nil)
	rec := httptest.NewRecorder()
	srv.login(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if !strings.Contains(rec.Body.String(), "/login-background.jpg") {
		t.Fatal("login page does not reference the background image")
	}
}

func testOAuthServer(t *testing.T, tokenURL, userInfoURL string) *server {
	t.Helper()

	srv, _ := testServer(t)
	srv.oauth = &oauthConfig{
		clientID:     "test-client",
		clientSecret: "test-secret",
		authorizeURL: "https://forum.test/forum/index.php?oauth2/authorize",
		tokenURL:     tokenURL,
		userInfoURL:  userInfoURL,
		scope:        "user:read",
		redirectURI:  "https://karte-test.example/auth/forum/callback",
	}
	srv.httpClient = &http.Client{Timeout: 5 * time.Second}
	return srv
}

func findCookie(cookies []*http.Cookie, name string) *http.Cookie {
	for _, cookie := range cookies {
		if cookie.Name == name {
			return cookie
		}
	}
	return nil
}

func TestOAuthLoginRedirectsToForum(t *testing.T) {
	srv := testOAuthServer(t, "https://forum.test/api/oauth2/token", "https://forum.test/api/me/")

	req := httptest.NewRequest(http.MethodGet, "/auth/forum/login?next=/karte.html", nil)
	rec := httptest.NewRecorder()
	srv.oauthLogin(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusSeeOther)
	}
	location := rec.Header().Get("Location")
	if !strings.Contains(location, "oauth2/authorize&") {
		t.Fatalf("authorize URL lost the XenForo query route: %q", location)
	}

	parsed, err := url.Parse(location)
	if err != nil {
		t.Fatal(err)
	}
	query := parsed.Query()
	if got := query.Get("response_type"); got != "code" {
		t.Errorf("response_type = %q", got)
	}
	if got := query.Get("client_id"); got != "test-client" {
		t.Errorf("client_id = %q", got)
	}
	if got := query.Get("redirect_uri"); got != "https://karte-test.example/auth/forum/callback" {
		t.Errorf("redirect_uri = %q", got)
	}
	if got := query.Get("scope"); got != "user:read" {
		t.Errorf("scope = %q", got)
	}
	state := query.Get("state")
	if state == "" {
		t.Fatal("state is empty")
	}

	cookie := findCookie(rec.Result().Cookies(), oauthStateCookieName)
	if cookie == nil {
		t.Fatal("state cookie was not set")
	}
	if !cookie.HttpOnly || !cookie.Secure {
		t.Error("state cookie is missing HttpOnly or Secure")
	}
	if cookie.SameSite != http.SameSiteLaxMode {
		t.Errorf("SameSite = %v", cookie.SameSite)
	}
	if cookie.Path != oauthStateCookiePath {
		t.Errorf("Path = %q", cookie.Path)
	}
	if cookie.MaxAge <= 0 {
		t.Errorf("MaxAge = %d", cookie.MaxAge)
	}
	gotState, gotNext, ok := verifyStateToken(srv.key, cookie.Value, srv.now())
	if !ok {
		t.Fatal("state cookie token is invalid")
	}
	if gotState != state {
		t.Errorf("state cookie state = %q, want %q", gotState, state)
	}
	if gotNext != "/karte.html" {
		t.Errorf("state cookie next = %q", gotNext)
	}
}

func TestLoginRedirectsToOAuthWhenEnabled(t *testing.T) {
	srv := testOAuthServer(t, "https://forum.test/api/oauth2/token", "https://forum.test/api/me/")

	req := httptest.NewRequest(http.MethodGet, "/login?next=/karte.html", nil)
	rec := httptest.NewRecorder()
	srv.login(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusSeeOther)
	}
	if got, want := rec.Header().Get("Location"), "/auth/forum/login?next=%2Fkarte.html"; got != want {
		t.Fatalf("Location = %q, want %q", got, want)
	}
}

func TestLoginLocalFallbackShowsOAuthButton(t *testing.T) {
	srv := testOAuthServer(t, "https://forum.test/api/oauth2/token", "https://forum.test/api/me/")

	req := httptest.NewRequest(http.MethodGet, "/login?local=1&next=/karte.html", nil)
	rec := httptest.NewRecorder()
	srv.login(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	body := rec.Body.String()
	if !strings.Contains(body, "Mit dem Velomobilforum anmelden") {
		t.Fatal("OAuth login button is missing")
	}
	if !strings.Contains(body, `href="/auth/forum/login?next=%2Fkarte.html"`) {
		t.Fatal("OAuth login button does not preserve next")
	}
	if !strings.Contains(body, `<form method="post" action="/login">`) {
		t.Fatal("local login form is missing")
	}
}

func TestLoginShowsFallbackOnOAuthError(t *testing.T) {
	srv := testOAuthServer(t, "https://forum.test/api/oauth2/token", "https://forum.test/api/me/")

	req := httptest.NewRequest(http.MethodGet, "/login?error=oauth&next=/karte.html", nil)
	rec := httptest.NewRecorder()
	srv.login(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	body := rec.Body.String()
	if !strings.Contains(body, "Anmeldung über das Velomobilforum derzeit nicht möglich.") {
		t.Fatal("OAuth error message is missing")
	}
	if !strings.Contains(body, "Mit dem Velomobilforum anmelden") {
		t.Fatal("OAuth retry button is missing")
	}
}

func TestOAuthDisabledKeepsLocalLogin(t *testing.T) {
	srv, _ := testServer(t)

	req := httptest.NewRequest(http.MethodGet, "/login?next=/karte.html", nil)
	rec := httptest.NewRecorder()
	srv.login(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	if strings.Contains(rec.Body.String(), "Mit dem Velomobilforum anmelden") {
		t.Fatal("OAuth login button is present without OAuth configuration")
	}
}

func TestOAuthCallbackSuccess(t *testing.T) {
	var tokenForm url.Values
	tokenSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("token method = %s", r.Method)
		}
		if err := r.ParseForm(); err != nil {
			t.Errorf("parse token form: %v", err)
		}
		tokenForm = r.PostForm
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"access_token":"access-123","token_type":"bearer","expires_in":3600,"refresh_token":"refresh-123"}`))
	}))
	defer tokenSrv.Close()

	var authorization string
	userSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authorization = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"me":{"user_id":123,"username":"velonaut"}}`))
	}))
	defer userSrv.Close()

	srv := testOAuthServer(t, tokenSrv.URL, userSrv.URL)
	state := "state-abc"
	stateToken := signStateToken(srv.key, srv.now().Add(10*time.Minute), state, "/karte.html")

	req := httptest.NewRequest(http.MethodGet, "/auth/forum/callback?code=code-123&state="+state, nil)
	req.AddCookie(&http.Cookie{Name: oauthStateCookieName, Value: stateToken})
	rec := httptest.NewRecorder()
	srv.oauthCallback(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusSeeOther)
	}
	if got := rec.Header().Get("Location"); got != "/karte.html" {
		t.Fatalf("Location = %q", got)
	}
	if got := tokenForm.Get("grant_type"); got != "authorization_code" {
		t.Errorf("grant_type = %q", got)
	}
	if got := tokenForm.Get("client_id"); got != "test-client" {
		t.Errorf("client_id = %q", got)
	}
	if got := tokenForm.Get("client_secret"); got != "test-secret" {
		t.Errorf("client_secret = %q", got)
	}
	if got := tokenForm.Get("code"); got != "code-123" {
		t.Errorf("code = %q", got)
	}
	if got := tokenForm.Get("redirect_uri"); got != "https://karte-test.example/auth/forum/callback" {
		t.Errorf("redirect_uri = %q", got)
	}
	if authorization != "Bearer access-123" {
		t.Errorf("Authorization = %q", authorization)
	}

	cookies := rec.Result().Cookies()
	session := findCookie(cookies, srv.cfg.cookieName)
	if session == nil {
		t.Fatal("session cookie was not set")
	}
	if !verifyToken(srv.key, session.Value, srv.now()) {
		t.Fatal("session cookie token is invalid")
	}
	stateCookie := findCookie(cookies, oauthStateCookieName)
	if stateCookie == nil || stateCookie.MaxAge >= 0 {
		t.Fatal("state cookie was not cleared")
	}
}

func TestOAuthCallbackRejectsBadState(t *testing.T) {
	tokenCalled := false
	tokenSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tokenCalled = true
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"access_token":"access-123","token_type":"bearer"}`))
	}))
	defer tokenSrv.Close()

	srv := testOAuthServer(t, tokenSrv.URL, "http://127.0.0.1:1/me")
	stateToken := signStateToken(srv.key, srv.now().Add(10*time.Minute), "good-state", "/karte.html")

	req := httptest.NewRequest(http.MethodGet, "/auth/forum/callback?code=code-123&state=bad-state", nil)
	req.AddCookie(&http.Cookie{Name: oauthStateCookieName, Value: stateToken})
	rec := httptest.NewRecorder()
	srv.oauthCallback(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusSeeOther)
	}
	if got := rec.Header().Get("Location"); !strings.HasPrefix(got, "/login?local=1&error=oauth") {
		t.Fatalf("Location = %q", got)
	}
	if tokenCalled {
		t.Fatal("token endpoint was called for an invalid state")
	}
	if findCookie(rec.Result().Cookies(), srv.cfg.cookieName) != nil {
		t.Fatal("session cookie was set for an invalid state")
	}
}

func TestOAuthCallbackTokenErrorRedirectsToFallback(t *testing.T) {
	tokenSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "invalid grant", http.StatusBadRequest)
	}))
	defer tokenSrv.Close()

	srv := testOAuthServer(t, tokenSrv.URL, "http://127.0.0.1:1/me")
	state := "state-abc"
	stateToken := signStateToken(srv.key, srv.now().Add(10*time.Minute), state, "/karte.html")

	req := httptest.NewRequest(http.MethodGet, "/auth/forum/callback?code=code-123&state="+state, nil)
	req.AddCookie(&http.Cookie{Name: oauthStateCookieName, Value: stateToken})
	rec := httptest.NewRecorder()
	srv.oauthCallback(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusSeeOther)
	}
	if got := rec.Header().Get("Location"); !strings.HasPrefix(got, "/login?local=1&error=oauth") {
		t.Fatalf("Location = %q", got)
	}
	if findCookie(rec.Result().Cookies(), srv.cfg.cookieName) != nil {
		t.Fatal("session cookie was set after a token error")
	}
}

func TestOAuthCallbackProviderErrorRedirectsToFallback(t *testing.T) {
	tokenCalled := false
	tokenSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tokenCalled = true
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"access_token":"access-123","token_type":"bearer"}`))
	}))
	defer tokenSrv.Close()

	srv := testOAuthServer(t, tokenSrv.URL, "http://127.0.0.1:1/me")
	state := "state-abc"
	stateToken := signStateToken(srv.key, srv.now().Add(10*time.Minute), state, "/karte.html")

	req := httptest.NewRequest(http.MethodGet, "/auth/forum/callback?error=access_denied&state="+state, nil)
	req.AddCookie(&http.Cookie{Name: oauthStateCookieName, Value: stateToken})
	rec := httptest.NewRecorder()
	srv.oauthCallback(rec, req)

	if rec.Code != http.StatusSeeOther {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusSeeOther)
	}
	if got := rec.Header().Get("Location"); !strings.HasPrefix(got, "/login?local=1&error=oauth") {
		t.Fatalf("Location = %q", got)
	}
	if tokenCalled {
		t.Fatal("token endpoint was called after a provider error")
	}
	if findCookie(rec.Result().Cookies(), srv.cfg.cookieName) != nil {
		t.Fatal("session cookie was set after a provider error")
	}
}

func TestOAuthStateToken(t *testing.T) {
	key := []byte("01234567890123456789012345678901")
	now := time.Unix(1_800_000_000, 0)

	token := signStateToken(key, now.Add(time.Hour), "state-abc", "/karte.html?x=1")
	state, next, ok := verifyStateToken(key, token, now)
	if !ok {
		t.Fatal("valid state token was rejected")
	}
	if state != "state-abc" {
		t.Errorf("state = %q", state)
	}
	if next != "/karte.html?x=1" {
		t.Errorf("next = %q", next)
	}
	if _, _, ok := verifyStateToken(key, token, now.Add(2*time.Hour)); ok {
		t.Fatal("expired state token was accepted")
	}
	if _, _, ok := verifyStateToken([]byte("another-key-that-is-long-enough-1234"), token, now); ok {
		t.Fatal("state token with wrong key was accepted")
	}
	if _, _, ok := verifyStateToken(key, token+"x", now); ok {
		t.Fatal("tampered state token was accepted")
	}
	if _, _, ok := verifyStateToken(key, "v1.bad", now); ok {
		t.Fatal("malformed state token was accepted")
	}
}

func TestLoadOAuthConfig(t *testing.T) {
	secretPath := filepath.Join(t.TempDir(), "oauth_client_secret")
	if err := os.WriteFile(secretPath, []byte("file-secret\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	t.Setenv("OAUTH_CLIENT_ID", "client-id")
	t.Setenv("OAUTH_CLIENT_SECRET", "")
	t.Setenv("OAUTH_CLIENT_SECRET_FILE", secretPath)
	t.Setenv("OAUTH_AUTHORIZE_URL", "https://forum.test/oauth2/authorize")
	t.Setenv("OAUTH_TOKEN_URL", "https://forum.test/api/oauth2/token")
	t.Setenv("OAUTH_USERINFO_URL", "https://forum.test/api/me/")
	t.Setenv("OAUTH_SCOPE", "user:read")
	t.Setenv("OAUTH_REDIRECT_URI", "https://karte-test.example/auth/forum/callback")

	cfg, err := loadOAuthConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg == nil {
		t.Fatal("OAuth config was not enabled")
	}
	if cfg.clientID != "client-id" || cfg.clientSecret != "file-secret" {
		t.Errorf("client credentials = %q / %q", cfg.clientID, cfg.clientSecret)
	}
	if cfg.scope != "user:read" {
		t.Errorf("scope = %q", cfg.scope)
	}

	t.Setenv("OAUTH_CLIENT_SECRET_FILE", "")
	t.Setenv("OAUTH_CLIENT_ID", "only-client-id")
	if _, err := loadOAuthConfig(); err == nil {
		t.Fatal("incomplete OAuth configuration was accepted")
	}

	for _, name := range []string{
		"OAUTH_CLIENT_ID", "OAUTH_CLIENT_SECRET", "OAUTH_CLIENT_SECRET_FILE",
		"OAUTH_AUTHORIZE_URL", "OAUTH_TOKEN_URL", "OAUTH_USERINFO_URL",
		"OAUTH_SCOPE", "OAUTH_REDIRECT_URI",
	} {
		t.Setenv(name, "")
	}
	cfg, err = loadOAuthConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg != nil {
		t.Fatal("OAuth config is enabled without environment values")
	}
}
