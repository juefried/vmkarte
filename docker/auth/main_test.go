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
