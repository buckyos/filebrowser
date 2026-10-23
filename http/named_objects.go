package fbhttp

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path"
	"strings"
	"time"

	"github.com/filebrowser/filebrowser/v2/files"
	"github.com/spf13/afero"
)

func namedStoreURL() (*url.URL, error) {
	endpoint := os.Getenv("BUCKYOS_NDM_URL")
	if endpoint == "" {
		endpoint = "http://127.0.0.1:3180"
	}
	u, err := url.Parse(endpoint)
	if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, fmt.Errorf("invalid BUCKYOS_NDM_URL")
	}
	return u, nil
}

func namedStoreProxy() handleFunc {
	return withUser(func(w http.ResponseWriter, r *http.Request, d *data) (int, error) {
		if !d.user.Perm.Create || !strings.HasPrefix(r.Header.Get("Authorization"), "Bearer ") {
			return http.StatusForbidden, nil
		}
		allowed := r.URL.Path == "/ndm/v1/uploads" || strings.HasPrefix(r.URL.Path, "/ndm/v1/uploads/") ||
			r.URL.Path == "/ndm/v1/objects/lookup" || r.URL.Path == "/ndm/v1/import/finalize" ||
			r.URL.Path == "/ndm/v1/store/is_object_stored" || r.URL.Path == "/ndm/v1/store/put_object"
		if !allowed {
			return http.StatusNotFound, nil
		}
		upstream, err := namedStoreURL()
		if err != nil {
			return http.StatusServiceUnavailable, err
		}
		proxy := httputil.NewSingleHostReverseProxy(upstream)
		director := proxy.Director
		proxy.Director = func(request *http.Request) {
			director(request)
			request.Header.Del("X-Auth")
			request.Header.Del("Cookie")
		}
		proxy.ModifyResponse = func(response *http.Response) error {
			if location := response.Header.Get("Location"); location != "" {
				parsed, parseErr := url.Parse(location)
				if parseErr != nil {
					return parseErr
				}
				if !strings.HasPrefix(parsed.Path, "/ndm/v1/uploads/") {
					return fmt.Errorf("unexpected upload location")
				}
				response.Header.Set("Location", d.server.BaseURL+"/api"+parsed.Path)
			}
			return nil
		}
		proxy.ServeHTTP(w, r)
		return 0, nil
	})
}

var namedStoreHTTP = &http.Client{
	Timeout:       60 * time.Minute,
	CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse },
}

func readNamedStore(ctx context.Context, upstream *url.URL, token, route, objID, inner string) (*http.Response, error) {
	body, err := json.Marshal(map[string]any{"obj_id": objID, "inner_path": inner})
	if err != nil {
		return nil, err
	}
	u := *upstream
	u.Path = strings.TrimSuffix(u.Path, "/") + route
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Authorization", token)
	request.Header.Set("Content-Type", "application/json")
	response, err := namedStoreHTTP.Do(request)
	if err != nil {
		return nil, err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		defer response.Body.Close()
		message, _ := io.ReadAll(io.LimitReader(response.Body, 1024))
		return nil, fmt.Errorf("named store %d: %s", response.StatusCode, message)
	}
	return response, nil
}

func safeNamedEntry(name string) bool {
	return name != "" && name != "." && name != ".." && !strings.ContainsAny(name, "/\\\x00:")
}

func lstatNamed(fs afero.Fs, name string) (os.FileInfo, bool, error) {
	if lstater, ok := fs.(afero.Lstater); ok {
		return lstater.LstatIfPossible(name)
	}
	return nil, false, fmt.Errorf("filesystem does not support safe object extraction")
}

func checkNamedDestination(d *data, target string) error {
	if !d.user.Perm.Create || !d.Check(target) {
		return os.ErrPermission
	}
	current := "/"
	for _, segment := range strings.Split(strings.Trim(target, "/"), "/") {
		if !safeNamedEntry(segment) {
			return fmt.Errorf("unsafe destination name")
		}
		current = path.Join(current, segment)
		info, _, err := lstatNamed(d.user.Fs, current)
		if os.IsNotExist(err) {
			continue
		}
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("symlink destinations are not supported")
		}
	}
	return nil
}

type extractionBudget struct {
	bytes   int64
	entries int
}

func extractNamedObject(ctx context.Context, d *data, upstream *url.URL, token, objID, inner, staged, target string, depth int, budget *extractionBudget) error {
	if depth > 256 || budget.entries >= 100000 {
		return fmt.Errorf("directory exceeds extraction limits")
	}
	budget.entries++
	if err := checkNamedDestination(d, target); err != nil {
		return err
	}
	response, err := readNamedStore(ctx, upstream, token, "/ndm/v1/store/open_object", objID, inner)
	if err != nil {
		return err
	}
	var envelope struct {
		Object string `json:"obj_data"`
	}
	err = json.NewDecoder(io.LimitReader(response.Body, 8<<20)).Decode(&envelope)
	response.Body.Close()
	if err != nil {
		return err
	}
	var object struct {
		Size    int64                      `json:"size"`
		Content string                     `json:"content"`
		Body    map[string]json.RawMessage `json:"body"`
	}
	if err = json.Unmarshal([]byte(envelope.Object), &object); err != nil {
		return err
	}
	if object.Body != nil {
		if err = d.user.Fs.Mkdir(staged, d.settings.DirMode); err != nil {
			return err
		}
		for name, child := range object.Body {
			if !safeNamedEntry(name) {
				return fmt.Errorf("unsafe directory entry: %q", name)
			}
			var childID string
			if json.Unmarshal(child, &childID) == nil {
				if !strings.HasPrefix(childID, "cyfile:") && !strings.HasPrefix(childID, "cydir:") {
					return fmt.Errorf("unsupported directory entry type")
				}
			} else {
				var inline struct {
					Kind string `json:"obj_type"`
				}
				if json.Unmarshal(child, &inline) != nil || (inline.Kind != "cyfile" && inline.Kind != "cydir") {
					return fmt.Errorf("unsupported inline directory entry type")
				}
			}
			if err = extractNamedObject(ctx, d, upstream, token, objID, path.Join(inner, name), path.Join(staged, name), path.Join(target, name), depth+1, budget); err != nil {
				return err
			}
		}
		return nil
	}
	if object.Size < 0 || object.Size > (64<<30)-budget.bytes {
		return fmt.Errorf("import exceeds 64 GiB extraction limit")
	}
	budget.bytes += object.Size
	output, err := d.user.Fs.OpenFile(staged, os.O_CREATE|os.O_EXCL|os.O_WRONLY, d.settings.FileMode)
	if err != nil {
		return err
	}
	defer output.Close()
	if object.Size == 0 && object.Content == "" {
		return nil
	}
	response, err = readNamedStore(ctx, upstream, token, "/ndm/proxy/v1/read/object/open", objID, inner)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	written, err := io.Copy(output, io.LimitReader(response.Body, object.Size+1))
	if err != nil {
		return err
	}
	if written != object.Size {
		return fmt.Errorf("named object size mismatch")
	}
	return output.Sync()
}

func equalExtracted(fs afero.Fs, left, right string) (bool, error) {
	a, err := fs.Stat(left)
	if err != nil {
		return false, err
	}
	b, _, err := lstatNamed(fs, right)
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if b.Mode()&os.ModeSymlink != 0 || a.IsDir() != b.IsDir() {
		return false, nil
	}
	if a.IsDir() {
		children, err := afero.ReadDir(fs, left)
		if err != nil {
			return false, err
		}
		others, err := afero.ReadDir(fs, right)
		if err != nil {
			return false, err
		}
		if len(children) != len(others) {
			return false, nil
		}
		for _, child := range children {
			equal, err := equalExtracted(fs, path.Join(left, child.Name()), path.Join(right, child.Name()))
			if err != nil || !equal {
				return equal, err
			}
		}
		return true, nil
	}
	if a.Size() != b.Size() {
		return false, nil
	}
	x, err := fs.Open(left)
	if err != nil {
		return false, err
	}
	defer x.Close()
	y, err := fs.Open(right)
	if err != nil {
		return false, err
	}
	defer y.Close()
	one, two := make([]byte, 64<<10), make([]byte, 64<<10)
	for {
		n, first := io.ReadFull(x, one)
		m, second := io.ReadFull(y, two)
		if n != m || !bytes.Equal(one[:n], two[:m]) {
			return false, nil
		}
		if first == io.EOF || first == io.ErrUnexpectedEOF {
			return second == first, nil
		}
		if first != nil {
			return false, first
		}
		if second != nil {
			return false, second
		}
	}
}

func recheckNamedTree(d *data, staged, target string) error {
	if err := checkNamedDestination(d, target); err != nil {
		return err
	}
	info, err := d.user.Fs.Stat(staged)
	if err != nil {
		return err
	}
	if !info.IsDir() {
		return nil
	}
	children, err := afero.ReadDir(d.user.Fs, staged)
	if err != nil {
		return err
	}
	for _, child := range children {
		if err := recheckNamedTree(d, path.Join(staged, child.Name()), path.Join(target, child.Name())); err != nil {
			return err
		}
	}
	return nil
}

func namedObjectPostHandler(fileCache FileCache) handleFunc {
	return withUser(func(w http.ResponseWriter, r *http.Request, d *data) (int, error) {
		target := strings.TrimSuffix(r.URL.Path, "/")
		if target == "" || target == "/" {
			return http.StatusBadRequest, fmt.Errorf("destination must name a file or folder")
		}
		if err := checkNamedDestination(d, target); err != nil {
			return http.StatusForbidden, err
		}
		token := r.Header.Get("Authorization")
		if !strings.HasPrefix(token, "Bearer ") {
			return http.StatusUnauthorized, nil
		}
		var request struct {
			ObjectID string `json:"obj_id"`
		}
		if err := json.NewDecoder(io.LimitReader(r.Body, 4096)).Decode(&request); err != nil {
			return http.StatusBadRequest, err
		}
		if !strings.HasPrefix(request.ObjectID, "cyfile:") && !strings.HasPrefix(request.ObjectID, "cydir:") {
			return http.StatusBadRequest, fmt.Errorf("expected FileObject or DirObject")
		}
		upstream, err := namedStoreURL()
		if err != nil {
			return http.StatusServiceUnavailable, err
		}
		base, err := afero.TempDir(d.user.Fs, path.Dir(target), ".ndm-import-")
		if err != nil {
			return errToStatus(err), err
		}
		defer d.user.Fs.RemoveAll(base)
		staged := path.Join(base, "content")
		budget := extractionBudget{}
		if err = extractNamedObject(r.Context(), d, upstream, token, request.ObjectID, "", staged, target, 0, &budget); err != nil {
			return http.StatusBadGateway, err
		}
		latestUser, err := d.store.Users.Get(d.server.Root, d.user.ID)
		if err != nil || latestUser.Scope != d.user.Scope {
			return http.StatusForbidden, fmt.Errorf("destination account changed during extraction")
		}
		latestSettings, err := d.store.Settings.Get()
		if err != nil {
			return http.StatusInternalServerError, err
		}
		d.user, d.settings = latestUser, latestSettings
		if err = recheckNamedTree(d, staged, target); err != nil {
			return http.StatusForbidden, err
		}
		if r.Context().Err() != nil {
			return http.StatusRequestTimeout, r.Context().Err()
		}
		existing, statErr := d.user.Fs.Stat(target)
		if statErr == nil {
			equal, compareErr := equalExtracted(d.user.Fs, staged, target)
			if compareErr != nil {
				return errToStatus(compareErr), compareErr
			}
			if equal {
				w.Header().Set("Content-Type", "application/json")
				return 0, json.NewEncoder(w).Encode(map[string]any{"obj_id": request.ObjectID, "reused": true})
			}
			if r.URL.Query().Get("override") != "true" || existing.IsDir() || strings.HasPrefix(request.ObjectID, "cydir:") {
				return http.StatusConflict, fmt.Errorf("destination exists; rename or skip the folder")
			}
			if !d.user.Perm.Modify {
				return http.StatusForbidden, nil
			}
			file, err := files.NewFileInfo(&files.FileOptions{Fs: d.user.Fs, Path: target, Modify: d.user.Perm.Modify, Expand: false, ReadHeader: d.server.TypeDetectionByHeader, Checker: d})
			if err != nil {
				return errToStatus(err), err
			}
			if err = delThumbs(r.Context(), fileCache, file); err != nil {
				return errToStatus(err), err
			}

		} else if !os.IsNotExist(statErr) {
			return errToStatus(statErr), statErr
		}
		err = d.RunHook(func() error { return d.user.Fs.Rename(staged, target) }, "upload", target, "", d.user)
		if err != nil {
			return errToStatus(err), err
		}
		w.Header().Set("Content-Type", "application/json")
		return 0, json.NewEncoder(w).Encode(map[string]any{"obj_id": request.ObjectID, "size": budget.bytes})
	})
}
