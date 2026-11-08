package main

import (
	"bytes"
	"encoding/json"
	"html/template"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func testLegalServer(t *testing.T) (*server, string) {
	t.Helper()

	srv, _ := testServer(t)
	dir := t.TempDir()
	legalDir := filepath.Join(dir, "legal")
	if err := os.MkdirAll(legalDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(legalDir, "impressum.html"),
		[]byte(`<h1>Impressum</h1><p>{{.Imprint.Name}}</p>`), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(legalDir, "datenschutz.html"),
		[]byte(`<h1>Datenschutz</h1><p>{{.Imprint.Email}}</p><p>Stand: {{.Updated}}</p>`), 0o600); err != nil {
		t.Fatal(err)
	}

	imprintPath := filepath.Join(dir, "impressum.json")
	if err := os.WriteFile(imprintPath, []byte(`{
		"name": "Max Mustermann",
		"street": "Musterstraße 1",
		"postal_code": "12345",
		"city": "Musterstadt",
		"country": "Deutschland",
		"email": "max@example.org",
		"updated": "2026-11-08"
	}`), 0o600); err != nil {
		t.Fatal(err)
	}
	imprintData, err := loadImprint(imprintPath)
	if err != nil {
		t.Fatal(err)
	}

	srv.cfg.imprint = imprintData
	srv.cfg.legalDir = legalDir
	return srv, legalDir
}

func serveLegal(srv *server, method, path string) *httptest.ResponseRecorder {
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(method, path, nil)
	switch path {
	case "/impressum":
		srv.imprintPage(rec, req)
	case "/datenschutz":
		srv.privacyPage(rec, req)
	default:
		panic("unknown legal path")
	}
	return rec
}

func TestLoadImprint(t *testing.T) {
	dir := t.TempDir()
	valid := filepath.Join(dir, "valid.json")
	if err := os.WriteFile(valid, []byte(`{
		"name": " Max Mustermann ",
		"street": "Musterstraße 1",
		"postal_code": "12345",
		"city": "Musterstadt",
		"country": "Deutschland",
		"email": "max@example.org",
		"updated": "2026-11-08"
	}`), 0o600); err != nil {
		t.Fatal(err)
	}
	data, err := loadImprint(valid)
	if err != nil {
		t.Fatal(err)
	}
	if data.Name != "Max Mustermann" {
		t.Fatalf("name not trimmed: %q", data.Name)
	}

	missing := filepath.Join(dir, "missing.json")
	if err := os.WriteFile(missing, []byte(`{"name":"Max"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := loadImprint(missing); err == nil {
		t.Fatal("incomplete imprint was accepted")
	}

	invalid := filepath.Join(dir, "invalid.json")
	if err := os.WriteFile(invalid, []byte(`{`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := loadImprint(invalid); err == nil {
		t.Fatal("invalid imprint was accepted")
	}

	if _, err := loadImprint(filepath.Join(dir, "absent.json")); err == nil {
		t.Fatal("missing imprint file was accepted")
	}
}

func TestLegalStatusWithoutConfig(t *testing.T) {
	srv, _ := testServer(t)

	rec := httptest.NewRecorder()
	srv.legalStatus(rec, httptest.NewRequest(http.MethodGet, "/legal-status", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	var status map[string]bool
	if err := json.Unmarshal(rec.Body.Bytes(), &status); err != nil {
		t.Fatal(err)
	}
	if status["privacy"] || status["imprint"] {
		t.Fatalf("legal pages enabled without config: %+v", status)
	}
}

func TestLegalStatusWithConfig(t *testing.T) {
	srv, _ := testLegalServer(t)

	rec := httptest.NewRecorder()
	srv.legalStatus(rec, httptest.NewRequest(http.MethodGet, "/legal-status", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	var status map[string]bool
	if err := json.Unmarshal(rec.Body.Bytes(), &status); err != nil {
		t.Fatal(err)
	}
	if !status["privacy"] || !status["imprint"] {
		t.Fatalf("legal pages disabled with config: %+v", status)
	}
}

func TestLegalPagesServeContent(t *testing.T) {
	srv, _ := testLegalServer(t)

	for _, tc := range []struct {
		path string
		want string
	}{
		{"/impressum", "Max Mustermann"},
		{"/datenschutz", "max@example.org"},
	} {
		rec := serveLegal(srv, http.MethodGet, tc.path)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s status = %d, want 200", tc.path, rec.Code)
		}
		if !strings.Contains(rec.Body.String(), tc.want) {
			t.Fatalf("%s does not contain %q", tc.path, tc.want)
		}
		if got := rec.Header().Get("X-Robots-Tag"); got != "noindex, nofollow" {
			t.Fatalf("%s X-Robots-Tag = %q", tc.path, got)
		}
		if got := rec.Header().Get("Cache-Control"); got != "no-store" {
			t.Fatalf("%s Cache-Control = %q", tc.path, got)
		}
	}
}

func TestLegalPagesNotFoundWithoutConfig(t *testing.T) {
	srv, _ := testServer(t)

	for _, path := range []string{"/impressum", "/datenschutz"} {
		rec := serveLegal(srv, http.MethodGet, path)
		if rec.Code != http.StatusNotFound {
			t.Fatalf("%s status = %d, want 404", path, rec.Code)
		}
	}
}

func TestLegalPagesRejectPost(t *testing.T) {
	srv, _ := testLegalServer(t)

	rec := serveLegal(srv, http.MethodPost, "/impressum")
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want 405", rec.Code)
	}
}

func TestLoginFooterShowsLegalLinks(t *testing.T) {
	configured, _ := testLegalServer(t)
	rec := httptest.NewRecorder()
	configured.login(rec, httptest.NewRequest(http.MethodGet, "/login", nil))
	body := rec.Body.String()
	if !strings.Contains(body, `href="/datenschutz"`) || !strings.Contains(body, `href="/impressum"`) {
		t.Fatal("login page does not contain legal links")
	}

	unconfigured, _ := testServer(t)
	rec = httptest.NewRecorder()
	unconfigured.login(rec, httptest.NewRequest(http.MethodGet, "/login", nil))
	body = rec.Body.String()
	if strings.Contains(body, `href="/datenschutz"`) || strings.Contains(body, `href="/impressum"`) {
		t.Fatal("login page contains legal links without config")
	}
}

func TestLegalPageEscapesImprintValues(t *testing.T) {
	srv, _ := testLegalServer(t)
	srv.cfg.imprint.Name = `<script>alert(1)</script>`

	rec := serveLegal(srv, http.MethodGet, "/impressum")
	body := rec.Body.String()
	if strings.Contains(body, "<script>alert(1)</script>") {
		t.Fatal("imprint value was not escaped")
	}
	if !strings.Contains(body, "&lt;script&gt;alert(1)&lt;/script&gt;") {
		t.Fatal("escaped imprint value not found")
	}
}

func TestLegalStatusRejectsPost(t *testing.T) {
	srv, _ := testServer(t)

	rec := httptest.NewRecorder()
	srv.legalStatus(rec, httptest.NewRequest(http.MethodPost, "/legal-status", nil))
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want 405", rec.Code)
	}
}

func TestLegalPageBackLinkUsesSession(t *testing.T) {
	srv, _ := testLegalServer(t)
	srv.now = func() time.Time { return time.Unix(1_800_000_000, 0) }

	rec := serveLegal(srv, http.MethodGet, "/impressum")
	if !strings.Contains(rec.Body.String(), `href="/"`) {
		t.Fatal("unauthenticated legal page is missing app link")
	}
	if !strings.Contains(rec.Body.String(), "Zur Anmeldung") {
		t.Fatal("unauthenticated legal page is missing login label")
	}
}

func TestLegalSamplesParse(t *testing.T) {
	data := legalContentData{
		Imprint: imprint{
			Name:       "Max Mustermann",
			Street:     "Musterstraße 1",
			PostalCode: "12345",
			City:       "Musterstadt",
			Country:    "Deutschland",
			Email:      "max@example.org",
			Updated:    "2026-11-08",
		},
		Updated: "2026-11-08",
	}

	for _, name := range []string{"impressum.html.sample", "datenschutz.html.sample"} {
		path := filepath.Join("..", "..", "config", "legal", name)
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		tmpl, err := template.New("content").Parse(string(raw))
		if err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		var body bytes.Buffer
		if err := tmpl.Execute(&body, data); err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		if body.Len() == 0 {
			t.Fatalf("%s: empty output", name)
		}
	}
}
