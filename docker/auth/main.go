package main

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	_ "embed"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"html/template"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"golang.org/x/crypto/bcrypt"
)

const (
	defaultListenAddr = ":8080"
	defaultPassword   = "/app/config/.htpasswd"
	defaultKeyFile    = "/run/secrets/session_signing_key"
	defaultCookieName = "vmkarte_session"
	defaultMaxAgeDays = 90
	maxLoginBody      = 8 << 10
	maxUsernameLen    = 128
	maxPasswordLen    = 1024

	oauthStateCookieName = "vmkarte_oauth_state"
	oauthStateCookiePath = "/auth/forum/"
	oauthStateLifetime   = 10 * time.Minute
	oauthHTTPTimeout     = 15 * time.Second
	oauthMaxResponseSize = 1 << 20
	oauthDefaultScope    = "user:read"
)

//go:embed assets/login-background.jpg
var loginBackgroundJPEG []byte

var loginTemplate = template.Must(template.New("login").Parse(`<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Anmeldung – Velomobilkarte</title>
<style>
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 1.5rem;
       font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
       background: #eef2ef url("/login-background.jpg?v=1") center / cover no-repeat;
       color: #14231b; }
body::before { content: ""; position: fixed; inset: 0; z-index: 0;
               background: rgba(238, 242, 239, 0.22); pointer-events: none; }
main { position: relative; z-index: 1; width: 100%; max-width: 24rem; padding: 2rem;
       border-radius: 1rem; background: #fff; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12); }
h1 { margin: 0 0 0.5rem; font-size: 1.5rem; }
p { margin: 0 0 1.25rem; color: #4b5d53; line-height: 1.45; }
label { display: block; margin-bottom: 1rem; font-weight: 600; }
input { width: 100%; margin-top: 0.35rem; padding: 0.7rem 0.8rem; border: 1px solid #a9b8af;
        border-radius: 0.5rem; font: inherit; background: #fff; color: inherit; }
input:focus { outline: 2px solid #2e7d32; outline-offset: 1px; border-color: #2e7d32; }
button { width: 100%; margin-top: 0.5rem; padding: 0.8rem 1rem; border: 0; border-radius: 0.5rem;
         font: inherit; font-weight: 700; color: #fff; background: #2e7d32; cursor: pointer; }
button:hover { background: #256428; }
.forum-login { display: block; margin: 0 0 1rem; padding: 0.8rem 1rem; border-radius: 0.5rem;
               font-weight: 700; text-align: center; text-decoration: none; color: #fff; background: #1565c0; }
.forum-login:hover { background: #0d47a1; }
.hint { margin: 0 0 0.75rem; color: #4b5d53; font-size: 0.9rem; }
.error { padding: 0.75rem; border-radius: 0.5rem; background: #fdecea; color: #8a1c16; }
@media (prefers-color-scheme: dark) {
  body { background-color: #101814; color: #e7efe9; }
  body::before { background: rgba(16, 24, 20, 0.55); }
  main { background: #1a2620; }
  p { color: #b7c8be; }
  .hint { color: #b7c8be; }
  input { background: #101814; border-color: #4f6558; }
  .error { background: #4a1b18; color: #ffd7d3; }
}
</style>
</head>
<body>
<main>
<h1>Velomobilkarte</h1>
{{if .OAuthEnabled}}
<p>Bitte mit dem Velomobilforum anmelden.</p>
<p><a class="forum-login" href="{{.OAuthURL}}">Mit dem Velomobilforum anmelden</a></p>
<p class="hint">Alternativ lokaler Fallback:</p>
{{else}}
<p>Bitte mit dem im Forum kommunizierten Zugang anmelden.</p>
{{end}}
{{if .Error}}<p class="error" role="alert">{{.Error}}</p>{{end}}
<form method="post" action="/login">
<input type="hidden" name="next" value="{{.Next}}">
<label>Benutzername
<input name="username" autocomplete="username" required autofocus value="{{.Username}}">
</label>
<label>Passwort
<input type="password" name="password" autocomplete="current-password" required>
</label>
<button type="submit">Anmelden</button>
</form>
</main>
</body>
</html>
`))

type oauthConfig struct {
	clientID     string
	clientSecret string
	authorizeURL string
	tokenURL     string
	userInfoURL  string
	scope        string
	redirectURI  string
}

type config struct {
	listenAddr   string
	passwordFile string
	keyFile      string
	cookieName   string
	cookieSecure bool
	cookieMaxAge time.Duration
	oauth        *oauthConfig
}

type loginData struct {
	Error        string
	Next         string
	Username     string
	OAuthEnabled bool
	OAuthURL     string
}

type server struct {
	cfg        config
	key        []byte
	oauth      *oauthConfig
	httpClient *http.Client
	dummyHash  []byte
	tmpl       *template.Template
	now        func() time.Time
}

func main() {
	cfg, err := loadConfig()
	if err != nil {
		slog.Error("invalid configuration", "error", err)
		os.Exit(1)
	}

	key, err := loadKey(cfg.keyFile)
	if err != nil {
		slog.Error("cannot load session signing key", "error", err)
		os.Exit(1)
	}

	srv, err := newServer(cfg, key)
	if err != nil {
		slog.Error("cannot initialize auth service", "error", err)
		os.Exit(1)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", srv.health)
	mux.HandleFunc("/login", srv.login)
	mux.HandleFunc("/login-background.jpg", srv.loginBackground)
	mux.HandleFunc("/logout", srv.logout)
	mux.HandleFunc("/session-check", srv.sessionCheck)
	mux.HandleFunc("/auth/forum/login", srv.oauthLogin)
	mux.HandleFunc("/auth/forum/callback", srv.oauthCallback)

	httpServer := &http.Server{
		Addr:              cfg.listenAddr,
		Handler:           loggingMiddleware(mux),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := httpServer.Shutdown(shutdownCtx); err != nil {
			slog.Error("graceful shutdown failed", "error", err)
		}
	}()

	slog.Info("auth service listening", "addr", cfg.listenAddr)
	if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		slog.Error("auth service stopped", "error", err)
		os.Exit(1)
	}
}

func newServer(cfg config, key []byte) (*server, error) {
	dummy, err := bcrypt.GenerateFromPassword([]byte("vmkarte-dummy-password"), 12)
	if err != nil {
		return nil, fmt.Errorf("create dummy hash: %w", err)
	}
	return &server{
		cfg:        cfg,
		key:        key,
		oauth:      cfg.oauth,
		httpClient: &http.Client{Timeout: oauthHTTPTimeout},
		dummyHash:  dummy,
		tmpl:       loginTemplate,
		now:        time.Now,
	}, nil
}

func loadConfig() (config, error) {
	maxAgeDays, err := strconv.Atoi(env("COOKIE_MAX_AGE_DAYS", strconv.Itoa(defaultMaxAgeDays)))
	if err != nil || maxAgeDays <= 0 || maxAgeDays > 3650 {
		return config{}, fmt.Errorf("COOKIE_MAX_AGE_DAYS must be between 1 and 3650")
	}

	secure, err := parseBool(env("COOKIE_SECURE", "true"))
	if err != nil {
		return config{}, fmt.Errorf("COOKIE_SECURE: %w", err)
	}

	cookieName := env("COOKIE_NAME", defaultCookieName)
	if strings.TrimSpace(cookieName) == "" {
		return config{}, fmt.Errorf("COOKIE_NAME must not be empty")
	}

	oauth, err := loadOAuthConfig()
	if err != nil {
		return config{}, err
	}

	return config{
		listenAddr:   env("LISTEN_ADDR", defaultListenAddr),
		passwordFile: env("PASSWORD_FILE", defaultPassword),
		keyFile:      env("SESSION_KEY_FILE", defaultKeyFile),
		cookieName:   cookieName,
		cookieSecure: secure,
		cookieMaxAge: time.Duration(maxAgeDays) * 24 * time.Hour,
		oauth:        oauth,
	}, nil
}

func loadOAuthConfig() (*oauthConfig, error) {
	clientID := strings.TrimSpace(os.Getenv("OAUTH_CLIENT_ID"))
	clientSecret := strings.TrimSpace(os.Getenv("OAUTH_CLIENT_SECRET"))
	secretFile := strings.TrimSpace(os.Getenv("OAUTH_CLIENT_SECRET_FILE"))
	authorizeURL := strings.TrimSpace(os.Getenv("OAUTH_AUTHORIZE_URL"))
	tokenURL := strings.TrimSpace(os.Getenv("OAUTH_TOKEN_URL"))
	userInfoURL := strings.TrimSpace(os.Getenv("OAUTH_USERINFO_URL"))
	scope := strings.TrimSpace(os.Getenv("OAUTH_SCOPE"))
	redirectURI := strings.TrimSpace(os.Getenv("OAUTH_REDIRECT_URI"))

	scopeExplicit := scope != ""
	if scope == "" {
		scope = oauthDefaultScope
	}

	if clientID == "" && clientSecret == "" && secretFile == "" &&
		authorizeURL == "" && tokenURL == "" && userInfoURL == "" &&
		!scopeExplicit && redirectURI == "" {
		return nil, nil
	}

	if secretFile != "" {
		raw, err := os.ReadFile(filepath.Clean(secretFile))
		if err != nil {
			return nil, fmt.Errorf("read OAUTH_CLIENT_SECRET_FILE: %w", err)
		}
		clientSecret = strings.TrimSpace(string(raw))
	}

	if clientID == "" || clientSecret == "" || authorizeURL == "" ||
		tokenURL == "" || userInfoURL == "" || redirectURI == "" {
		return nil, fmt.Errorf("incomplete OAuth configuration")
	}

	return &oauthConfig{
		clientID:     clientID,
		clientSecret: clientSecret,
		authorizeURL: authorizeURL,
		tokenURL:     tokenURL,
		userInfoURL:  userInfoURL,
		scope:        scope,
		redirectURI:  redirectURI,
	}, nil
}

func env(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func parseBool(value string) (bool, error) {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "yes", "on":
		return true, nil
	case "0", "false", "no", "off":
		return false, nil
	default:
		return false, fmt.Errorf("invalid boolean %q", value)
	}
}

func loadKey(path string) ([]byte, error) {
	raw, err := os.ReadFile(filepath.Clean(path))
	if err != nil {
		return nil, err
	}

	text := strings.TrimSpace(string(raw))
	decoders := []*base64.Encoding{
		base64.StdEncoding,
		base64.RawStdEncoding,
		base64.RawURLEncoding,
	}
	for _, decoder := range decoders {
		if decoded, err := decoder.DecodeString(text); err == nil && len(decoded) >= 32 {
			return decoded, nil
		}
	}
	if len(text) >= 32 {
		return []byte(text), nil
	}
	return nil, fmt.Errorf("session signing key must contain at least 32 bytes")
}

func (s *server) health(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", http.MethodGet)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	_, _ = w.Write([]byte("ok\n"))
}

func (s *server) loginBackground(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		w.Header().Set("Allow", "GET, HEAD")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "image/jpeg")
	w.Header().Set("Cache-Control", "public, max-age=604800")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Content-Length", strconv.Itoa(len(loginBackgroundJPEG)))
	if r.Method == http.MethodHead {
		w.WriteHeader(http.StatusOK)
		return
	}
	_, _ = w.Write(loginBackgroundJPEG)
}

func (s *server) oauthLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", http.MethodGet)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	next := sanitizeNext(r.URL.Query().Get("next"), "/")
	if s.oauth == nil {
		http.Redirect(w, r, "/login?local=1&next="+url.QueryEscape(next), http.StatusSeeOther)
		return
	}

	stateBytes := make([]byte, 32)
	if _, err := rand.Read(stateBytes); err != nil {
		slog.Error("cannot create OAuth state", "error", err)
		s.redirectOAuthError(w, r, next)
		return
	}
	state := base64.RawURLEncoding.EncodeToString(stateBytes)
	expires := s.now().Add(oauthStateLifetime)

	s.setOAuthStateCookie(w, signStateToken(s.key, expires, state, next), expires)
	w.Header().Set("Cache-Control", "no-store")
	http.Redirect(w, r, s.oauthAuthorizeURL(state), http.StatusSeeOther)
}

func (s *server) oauthCallback(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", http.MethodGet)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	cookie, err := r.Cookie(oauthStateCookieName)
	if err != nil {
		s.redirectOAuthError(w, r, "/")
		return
	}

	state, stateNext, ok := verifyStateToken(s.key, cookie.Value, s.now())
	if !ok {
		s.clearOAuthStateCookie(w)
		s.redirectOAuthError(w, r, "/")
		return
	}
	next := sanitizeNext(stateNext, "/")
	s.clearOAuthStateCookie(w)

	if s.oauth == nil {
		s.redirectOAuthError(w, r, next)
		return
	}
	if providerError := r.URL.Query().Get("error"); providerError != "" {
		slog.Warn("OAuth provider returned an error", "error", providerError)
		s.redirectOAuthError(w, r, next)
		return
	}
	if subtle.ConstantTimeCompare([]byte(state), []byte(r.URL.Query().Get("state"))) != 1 {
		s.redirectOAuthError(w, r, next)
		return
	}
	code := r.URL.Query().Get("code")
	if code == "" {
		s.redirectOAuthError(w, r, next)
		return
	}

	token, err := s.exchangeOAuthCode(r.Context(), code)
	if err != nil {
		slog.Error("OAuth token exchange failed", "error", err)
		s.redirectOAuthError(w, r, next)
		return
	}

	user, err := s.fetchOAuthUser(r.Context(), token.AccessToken)
	if err != nil {
		slog.Error("OAuth user lookup failed", "error", err)
		s.redirectOAuthError(w, r, next)
		return
	}

	nonce := make([]byte, 32)
	if _, err := rand.Read(nonce); err != nil {
		slog.Error("cannot create session nonce", "error", err)
		s.redirectOAuthError(w, r, next)
		return
	}
	expires := s.now().Add(s.cfg.cookieMaxAge)
	s.setSessionCookie(w, signToken(s.key, expires, nonce), expires)
	slog.Info("OAuth login", "user_id", user.Me.ID, "username", user.Me.Username)
	w.Header().Set("Cache-Control", "no-store")
	http.Redirect(w, r, next, http.StatusSeeOther)
}

func (s *server) oauthAuthorizeURL(state string) string {
	params := url.Values{}
	params.Set("response_type", "code")
	params.Set("client_id", s.oauth.clientID)
	params.Set("redirect_uri", s.oauth.redirectURI)
	params.Set("scope", s.oauth.scope)
	params.Set("state", state)

	separator := "?"
	if strings.Contains(s.oauth.authorizeURL, "?") {
		separator = "&"
	}
	return s.oauth.authorizeURL + separator + params.Encode()
}

func (s *server) setOAuthStateCookie(w http.ResponseWriter, token string, expires time.Time) {
	http.SetCookie(w, &http.Cookie{
		Name:     oauthStateCookieName,
		Value:    token,
		Path:     oauthStateCookiePath,
		HttpOnly: true,
		Secure:   s.cfg.cookieSecure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   int(oauthStateLifetime / time.Second),
		Expires:  expires,
	})
}

func (s *server) clearOAuthStateCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     oauthStateCookieName,
		Value:    "",
		Path:     oauthStateCookiePath,
		HttpOnly: true,
		Secure:   s.cfg.cookieSecure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
		Expires:  time.Unix(1, 0),
	})
}

func (s *server) redirectOAuthError(w http.ResponseWriter, r *http.Request, next string) {
	next = sanitizeNext(next, "/")
	http.Redirect(w, r, "/login?local=1&error=oauth&next="+url.QueryEscape(next), http.StatusSeeOther)
}

func signStateToken(key []byte, expires time.Time, state, next string) string {
	payload := "v1." + strconv.FormatInt(expires.Unix(), 10) + "." + state + "." +
		base64.RawURLEncoding.EncodeToString([]byte(next))
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte(payload))
	return payload + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func verifyStateToken(key []byte, token string, now time.Time) (string, string, bool) {
	parts := strings.Split(token, ".")
	if len(parts) != 5 || parts[0] != "v1" {
		return "", "", false
	}
	expires, err := strconv.ParseInt(parts[1], 10, 64)
	if err != nil || now.Unix() >= expires {
		return "", "", false
	}
	if parts[2] == "" {
		return "", "", false
	}
	nextBytes, err := base64.RawURLEncoding.DecodeString(parts[3])
	if err != nil {
		return "", "", false
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[4])
	if err != nil {
		return "", "", false
	}
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte("v1." + parts[1] + "." + parts[2] + "." + parts[3]))
	if !hmac.Equal(mac.Sum(nil), signature) {
		return "", "", false
	}
	return parts[2], string(nextBytes), true
}

type oauthTokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"`
	Scope        string `json:"scope"`
}

type oauthErrorResponse struct {
	Error            string `json:"error"`
	ErrorDescription string `json:"error_description"`
}

type oauthUser struct {
	ID       int64  `json:"user_id"`
	Username string `json:"username"`
	IsBanned bool   `json:"is_banned"`
}

type oauthUserResponse struct {
	Me oauthUser `json:"me"`
}

func (s *server) exchangeOAuthCode(ctx context.Context, code string) (*oauthTokenResponse, error) {
	form := url.Values{}
	form.Set("client_id", s.oauth.clientID)
	form.Set("client_secret", s.oauth.clientSecret)
	form.Set("grant_type", "authorization_code")
	form.Set("code", code)
	form.Set("redirect_uri", s.oauth.redirectURI)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, s.oauth.tokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return nil, fmt.Errorf("create token request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Accept", "application/json")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("token request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		var providerError oauthErrorResponse
		if err := json.Unmarshal(body, &providerError); err == nil && providerError.Error != "" {
			if providerError.ErrorDescription != "" {
				return nil, fmt.Errorf("token endpoint returned HTTP %d: %s: %s",
					resp.StatusCode, providerError.Error, providerError.ErrorDescription)
			}
			return nil, fmt.Errorf("token endpoint returned HTTP %d: %s",
				resp.StatusCode, providerError.Error)
		}
		return nil, fmt.Errorf("token endpoint returned HTTP %d", resp.StatusCode)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, oauthMaxResponseSize))
	if err != nil {
		return nil, fmt.Errorf("read token response: %w", err)
	}
	var token oauthTokenResponse
	if err := json.Unmarshal(body, &token); err != nil {
		return nil, fmt.Errorf("decode token response: %w", err)
	}
	if strings.TrimSpace(token.AccessToken) == "" {
		return nil, fmt.Errorf("token response has no access token")
	}
	if !strings.EqualFold(token.TokenType, "bearer") {
		return nil, fmt.Errorf("unexpected token type %q", token.TokenType)
	}
	return &token, nil
}

func (s *server) fetchOAuthUser(ctx context.Context, accessToken string) (*oauthUserResponse, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, s.oauth.userInfoURL, nil)
	if err != nil {
		return nil, fmt.Errorf("create userinfo request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+accessToken)
	req.Header.Set("Accept", "application/json")

	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("userinfo request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("userinfo endpoint returned HTTP %d", resp.StatusCode)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, oauthMaxResponseSize))
	if err != nil {
		return nil, fmt.Errorf("read userinfo response: %w", err)
	}
	var user oauthUserResponse
	if err := json.Unmarshal(body, &user); err != nil {
		return nil, fmt.Errorf("decode userinfo response: %w", err)
	}
	if user.Me.ID <= 0 || strings.TrimSpace(user.Me.Username) == "" {
		return nil, fmt.Errorf("userinfo response is missing user_id or username")
	}
	if user.Me.IsBanned {
		return nil, fmt.Errorf("forum user is banned")
	}
	return &user, nil
}

func (s *server) login(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		next := sanitizeNext(r.URL.Query().Get("next"), "/")
		if s.sessionValid(r) {
			http.Redirect(w, r, next, http.StatusSeeOther)
			return
		}
		if s.oauth != nil && r.URL.Query().Get("local") != "1" && r.URL.Query().Get("error") == "" {
			http.Redirect(w, r, "/auth/forum/login?next="+url.QueryEscape(next), http.StatusSeeOther)
			return
		}
		data := loginData{Next: next}
		if r.URL.Query().Get("error") == "oauth" {
			data.Error = "Anmeldung über das Velomobilforum derzeit nicht möglich."
		}
		if s.oauth != nil {
			data.OAuthEnabled = true
			data.OAuthURL = "/auth/forum/login?next=" + url.QueryEscape(next)
		}
		s.renderLogin(w, http.StatusOK, data)
	case http.MethodPost:
		if isCrossSite(r) {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		s.handleLoginPost(w, r)
	default:
		w.Header().Set("Allow", "GET, POST")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (s *server) handleLoginPost(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, maxLoginBody)
	if err := r.ParseForm(); err != nil {
		s.renderLogin(w, http.StatusBadRequest, loginData{
			Error: "Anmeldung nicht möglich.",
			Next:  "/",
		})
		return
	}

	username := strings.TrimSpace(r.PostFormValue("username"))
	password := r.PostFormValue("password")
	next := sanitizeNext(r.PostFormValue("next"), "/")

	if username == "" || password == "" || len(username) > maxUsernameLen || len(password) > maxPasswordLen {
		s.renderLogin(w, http.StatusUnauthorized, loginData{
			Error:    "Anmeldung nicht möglich.",
			Next:     next,
			Username: username,
		})
		return
	}

	hash, found, err := readCredentials(s.cfg.passwordFile, username)
	if err != nil {
		slog.Error("cannot read password file", "error", err)
		s.renderLogin(w, http.StatusInternalServerError, loginData{
			Error:    "Anmeldung derzeit nicht möglich.",
			Next:     next,
			Username: username,
		})
		return
	}

	passwordBytes := []byte(password)
	if !found {
		_ = bcrypt.CompareHashAndPassword(s.dummyHash, passwordBytes)
		s.renderLogin(w, http.StatusUnauthorized, loginData{
			Error:    "Anmeldung nicht möglich.",
			Next:     next,
			Username: username,
		})
		return
	}

	if err := bcrypt.CompareHashAndPassword(hash, passwordBytes); err != nil {
		s.renderLogin(w, http.StatusUnauthorized, loginData{
			Error:    "Anmeldung nicht möglich.",
			Next:     next,
			Username: username,
		})
		return
	}

	nonce := make([]byte, 32)
	if _, err := rand.Read(nonce); err != nil {
		slog.Error("cannot create session nonce", "error", err)
		s.renderLogin(w, http.StatusInternalServerError, loginData{
			Error:    "Anmeldung derzeit nicht möglich.",
			Next:     next,
			Username: username,
		})
		return
	}

	expires := s.now().Add(s.cfg.cookieMaxAge)
	s.setSessionCookie(w, signToken(s.key, expires, nonce), expires)
	w.Header().Set("Cache-Control", "no-store")
	http.Redirect(w, r, next, http.StatusSeeOther)
}

func (s *server) logout(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet && r.Method != http.MethodPost {
		w.Header().Set("Allow", "GET, POST")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if r.Method == http.MethodPost && isCrossSite(r) {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	// TODO: Revoke the forum access/refresh token once tokens are stored
	// server-side and logout should also end the forum authorization.
	s.clearSessionCookie(w)
	w.Header().Set("Cache-Control", "no-store")
	http.Redirect(w, r, "/login", http.StatusSeeOther)
}

func (s *server) sessionCheck(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", http.MethodGet)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	if !s.sessionValid(r) {
		w.WriteHeader(http.StatusUnauthorized)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *server) renderLogin(w http.ResponseWriter, status int, data loginData) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Frame-Options", "DENY")
	w.WriteHeader(status)
	if err := s.tmpl.Execute(w, data); err != nil {
		slog.Error("cannot render login page", "error", err)
	}
}

func (s *server) sessionValid(r *http.Request) bool {
	cookie, err := r.Cookie(s.cfg.cookieName)
	if err != nil {
		return false
	}
	return verifyToken(s.key, cookie.Value, s.now())
}

func (s *server) setSessionCookie(w http.ResponseWriter, token string, expires time.Time) {
	http.SetCookie(w, &http.Cookie{
		Name:     s.cfg.cookieName,
		Value:    token,
		Path:     "/",
		HttpOnly: true,
		Secure:   s.cfg.cookieSecure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   int(s.cfg.cookieMaxAge / time.Second),
		Expires:  expires,
	})
}

func (s *server) clearSessionCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     s.cfg.cookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   s.cfg.cookieSecure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
		Expires:  time.Unix(1, 0),
	})
}

func readCredentials(path, username string) ([]byte, bool, error) {
	raw, err := os.ReadFile(filepath.Clean(path))
	if err != nil {
		return nil, false, err
	}

	var lastHash, lastBcrypt string
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(strings.TrimSuffix(line, "\r"))
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		user, hash, ok := strings.Cut(line, ":")
		if !ok {
			continue
		}
		if subtle.ConstantTimeCompare([]byte(strings.TrimSpace(user)), []byte(username)) != 1 {
			continue
		}
		normalized := normalizeBcrypt(strings.TrimSpace(hash))
		lastHash = normalized
		if isBcryptHash(normalized) {
			lastBcrypt = normalized
		}
	}

	// A legacy $apr1$ line may still precede a newly appended bcrypt line.
	// Prefer the last bcrypt entry so the bcrypt migration works without
	// manually rewriting an existing file first.
	if lastBcrypt != "" {
		return []byte(lastBcrypt), true, nil
	}
	if lastHash != "" {
		return []byte(lastHash), true, nil
	}
	return nil, false, nil
}

func isBcryptHash(hash string) bool {
	return strings.HasPrefix(hash, "$2a$") ||
		strings.HasPrefix(hash, "$2b$") ||
		strings.HasPrefix(hash, "$2y$")
}

func normalizeBcrypt(hash string) string {
	if strings.HasPrefix(hash, "$2y$") {
		return "$2b$" + strings.TrimPrefix(hash, "$2y$")
	}
	return hash
}

func signToken(key []byte, expires time.Time, nonce []byte) string {
	payload := "v1." + strconv.FormatInt(expires.Unix(), 10) + "." + base64.RawURLEncoding.EncodeToString(nonce)
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte(payload))
	return payload + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func verifyToken(key []byte, token string, now time.Time) bool {
	parts := strings.Split(token, ".")
	if len(parts) != 4 || parts[0] != "v1" {
		return false
	}
	expires, err := strconv.ParseInt(parts[1], 10, 64)
	if err != nil || now.Unix() >= expires {
		return false
	}
	if _, err := base64.RawURLEncoding.DecodeString(parts[2]); err != nil {
		return false
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[3])
	if err != nil {
		return false
	}
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte("v1." + parts[1] + "." + parts[2]))
	return hmac.Equal(mac.Sum(nil), signature)
}

func sanitizeNext(value, fallback string) string {
	if value == "" {
		return fallback
	}
	if !strings.HasPrefix(value, "/") || strings.HasPrefix(value, "//") {
		return fallback
	}
	if strings.ContainsAny(value, "\\\r\n") {
		return fallback
	}
	if value == "/login" || strings.HasPrefix(value, "/login?") || value == "/logout" {
		return fallback
	}
	return value
}

func isCrossSite(r *http.Request) bool {
	if strings.EqualFold(r.Header.Get("Sec-Fetch-Site"), "cross-site") {
		return true
	}

	origin := strings.TrimSpace(r.Header.Get("Origin"))
	if origin == "" {
		return false
	}
	parsed, err := url.Parse(origin)
	if err != nil || parsed.Hostname() == "" {
		return true
	}

	host := r.Host
	if forwarded := r.Header.Get("X-Forwarded-Host"); forwarded != "" {
		host = strings.TrimSpace(strings.Split(forwarded, ",")[0])
	}
	if splitHost, _, err := net.SplitHostPort(host); err == nil {
		host = splitHost
	}
	return !strings.EqualFold(parsed.Hostname(), host)
}

func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		recorder := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(recorder, r)
		slog.Info("request",
			"method", r.Method,
			"path", r.URL.Path,
			"status", recorder.status,
			"duration", time.Since(start).Round(time.Millisecond),
		)
	})
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(status int) {
	r.status = status
	r.ResponseWriter.WriteHeader(status)
}
