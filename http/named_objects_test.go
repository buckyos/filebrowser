package fbhttp

import (
	"bytes"
	"context"
	"encoding/json"
	"github.com/asdine/storm/v3"
	"github.com/filebrowser/filebrowser/v2/settings"
	"github.com/filebrowser/filebrowser/v2/storage/bolt"
	"github.com/filebrowser/filebrowser/v2/users"
	"github.com/golang-jwt/jwt/v5"
	"github.com/spf13/afero"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func extractionData(t *testing.T) (*data, string) {
	t.Helper()
	root := t.TempDir()
	return &data{user: &users.User{Fs: afero.NewBasePathFs(afero.NewOsFs(), root), Perm: users.Permissions{Create: true, Modify: true}}, settings: &settings.Settings{DirMode: 0700, FileMode: 0600}}, root
}

func TestNamedObjectExtractionUsesAuthorizedRootAndPreservesTree(t *testing.T) {
	d, root := extractionData(t)
	reads := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer user-app-session" {
			t.Error("missing user session")
			w.WriteHeader(403)
			return
		}
		var request struct {
			Object string `json:"obj_id"`
			Inner  string `json:"inner_path"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
			return
		}
		if request.Object != "cydir:root" {
			t.Error("must authorize reads against the imported root")
		}
		if r.URL.Path == "/ndm/proxy/v1/read/object/open" {
			reads++
			_, _ = w.Write([]byte("firstsecond"))
			return
		}
		var object any
		switch request.Inner {
		case "":
			object = map[string]any{"body": map[string]string{"empty": "cydir:empty", "数据.txt": "cyfile:data"}}
		case "empty":
			object = map[string]any{"body": map[string]string{}}
		case "数据.txt":
			object = map[string]any{"size": 11, "content": "clist:chunks"}
		default:
			t.Errorf("unexpected inner path %q", request.Inner)
		}
		body, _ := json.Marshal(object)
		_ = json.NewEncoder(w).Encode(map[string]string{"obj_data": string(body)})
	}))
	defer upstream.Close()
	u, _ := url.Parse(upstream.URL)
	budget := extractionBudget{}
	if err := extractNamedObject(context.Background(), d, u, "Bearer user-app-session", "cydir:root", "", "/staged", "/destination", 0, &budget); err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(filepath.Join(root, "staged", "数据.txt"))
	if err != nil || string(content) != "firstsecond" {
		t.Fatalf("extracted content %q: %v", content, err)
	}
	if stat, err := os.Stat(filepath.Join(root, "staged", "empty")); err != nil || !stat.IsDir() {
		t.Fatal("missing empty directory")
	}
	if reads != 1 || budget.bytes != 11 {
		t.Fatalf("reads=%d bytes=%d", reads, budget.bytes)
	}
	if equal, err := equalExtracted(d.user.Fs, "/staged", "/staged"); err != nil || !equal {
		t.Fatal("retry comparison failed")
	}
	if err := afero.WriteFile(d.user.Fs, "/different", []byte("firstsecond!"), 0600); err != nil {
		t.Fatal(err)
	}
	if equal, _ := equalExtracted(d.user.Fs, "/staged/数据.txt", "/different"); equal {
		t.Fatal("different content considered idempotent")
	}
}

func TestNamedObjectExtractionRejectsUnsafeNamesSymlinksAndOversize(t *testing.T) {
	for _, name := range []string{"", ".", "..", "../escape", "a/b", "a\\b", "C:", "bad\x00name"} {
		if safeNamedEntry(name) {
			t.Errorf("unsafe name accepted: %q", name)
		}
	}
	d, root := extractionData(t)
	outside := t.TempDir()
	if err := os.Symlink(outside, filepath.Join(root, "linked")); err != nil {
		t.Fatal(err)
	}
	if err := checkNamedDestination(d, "/linked/file"); err == nil {
		t.Fatal("symlink destination accepted")
	}
	d.user.Perm.Create = false
	if err := checkNamedDestination(d, "/new"); err == nil {
		t.Fatal("readonly destination accepted")
	}
	d.user.Perm.Create = true
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/ndm/v1/store/open_object" {
			t.Error("oversize object was read")
		}
		_ = json.NewEncoder(w).Encode(map[string]string{"obj_data": `{"size":68719476737,"content":"clist:huge"}`})
	}))
	defer upstream.Close()
	u, _ := url.Parse(upstream.URL)
	if err := extractNamedObject(context.Background(), d, u, "Bearer token", "cyfile:huge", "", "/staged", "/destination", 0, &extractionBudget{}); err == nil {
		t.Fatal("oversize object accepted")
	}
	if _, err := os.Stat(filepath.Join(root, "staged")); !os.IsNotExist(err) {
		t.Fatal("oversize object created a file")
	}
}

type namedTestCache struct{}

func (namedTestCache) Store(context.Context, string, []byte) error        { return nil }
func (namedTestCache) Load(context.Context, string) ([]byte, bool, error) { return nil, false, nil }
func (namedTestCache) Delete(context.Context, string) error               { return nil }

func TestNamedObjectCommitPreservesPermissionsConflictsAndRetry(t *testing.T) {
	root := t.TempDir()
	db, err := storm.Open(filepath.Join(t.TempDir(), "db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := bolt.NewStorage(db)
	if err != nil {
		t.Fatal(err)
	}
	config := &settings.Settings{Key: []byte("test-key"), FileMode: 0600, DirMode: 0700}
	if err = store.Settings.Save(config); err != nil {
		t.Fatal(err)
	}
	user := &users.User{Username: "alice", Password: "unused", Scope: ".", Perm: users.Permissions{Create: true, Modify: true}}
	if err = store.Users.Save(user); err != nil {
		t.Fatal(err)
	}
	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, authToken{User: userInfo{ID: user.ID}, RegisteredClaims: jwt.RegisteredClaims{ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour))}}).SignedString(config.Key)
	if err != nil {
		t.Fatal(err)
	}
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer alice-zone-session" {
			t.Error("original Zone session missing")
			w.WriteHeader(403)
			return
		}
		var request struct {
			ID    string `json:"obj_id"`
			Inner string `json:"inner_path"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
			return
		}
		if request.ID == "cyfile:revoke" {
			user.Perm.Create = false
			if err := store.Users.Update(user, "Perm"); err != nil {
				t.Error(err)
			}
		}
		content := "original"
		if request.ID == "cyfile:new" {
			content = "replacement"
		}
		if strings.Contains(r.URL.Path, "/read/object/open") {
			_, _ = w.Write([]byte(content))
			return
		}
		var object any = map[string]any{"size": len(content), "content": "sha256:content"}
		if request.ID == "cydir:folder" {
			if request.Inner == "" {
				object = map[string]any{"body": map[string]string{"leaf.txt": "cyfile:leaf", "empty": "cydir:empty"}}
			}
			if request.Inner == "empty" {
				object = map[string]any{"body": map[string]string{}}
			}
		}
		body, _ := json.Marshal(object)
		_ = json.NewEncoder(w).Encode(map[string]string{"obj_data": string(body)})
	}))
	defer upstream.Close()
	t.Setenv("BUCKYOS_NDM_URL", upstream.URL)
	handler := handle(namedObjectPostHandler(namedTestCache{}), "", store, &settings.Server{Root: root})
	commit := func(target, id string, expected int) {
		t.Helper()
		body, _ := json.Marshal(map[string]string{"obj_id": id})
		request := httptest.NewRequest(http.MethodPost, target, bytes.NewReader(body))
		request.Header.Set("X-Auth", token)
		request.Header.Set("Authorization", "Bearer alice-zone-session")
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != expected {
			t.Fatalf("commit %s: %d %s", target, response.Code, response.Body.String())
		}
		entries, err := os.ReadDir(root)
		if err != nil {
			t.Fatal(err)
		}
		for _, entry := range entries {
			if strings.HasPrefix(entry.Name(), ".ndm-import-") {
				t.Fatal("staging leaked")
			}
		}
	}
	read := func(name, expected string) {
		t.Helper()
		content, err := os.ReadFile(filepath.Join(root, name))
		if err != nil || string(content) != expected {
			t.Fatalf("readback %s: %q %v", name, content, err)
		}
	}
	commit("/file.txt", "cyfile:old", 200)
	commit("/file.txt", "cyfile:old", 200) // response loss: idempotent destination retry
	commit("/file.txt", "cyfile:new", 409)
	read("file.txt", "original")
	commit("/renamed.txt", "cyfile:new", 200)
	read("renamed.txt", "replacement")
	commit("/file.txt?override=true", "cyfile:new", 200)
	read("file.txt", "replacement")
	commit("/folder", "cydir:folder", 200)
	read("folder/leaf.txt", "original")
	if info, err := os.Stat(filepath.Join(root, "folder/empty")); err != nil || !info.IsDir() {
		t.Fatal("empty directory missing")
	}
	commit("/folder", "cydir:folder", 200)
	if err := os.WriteFile(filepath.Join(root, "folder/leaf.txt"), []byte("local edit"), 0600); err != nil {
		t.Fatal(err)
	}
	commit("/folder?override=true", "cydir:folder", 409)
	read("folder/leaf.txt", "local edit")
	commit("/revoked.txt", "cyfile:revoke", 403)
	if _, err := os.Stat(filepath.Join(root, "revoked.txt")); !os.IsNotExist(err) {
		t.Fatal("revoked destination was written")
	}
}
