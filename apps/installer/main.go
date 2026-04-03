/*
Nodeadline V2 installer: version.json + manifest + verified payload, venv, supervise node.

Windows: logs always go to %LOCALAPPDATA%/nodeadline-v2/runtime/installer.log
so you can diagnose when the console window closes immediately.
*/
package main

import (
	"archive/tar"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	defaultBase = "https://nodeadline.online"
	tickEvery   = 30 * time.Second
)

// lastPayloadIdleLog throttles "up to date" log lines (single sync goroutine + main before loop).
var lastPayloadIdleLog time.Time

// noCacheRoundTripper forces fresh manifest/version through proxies and browser-style caches (Windows).
type noCacheRoundTripper struct{ next http.RoundTripper }

func (n *noCacheRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	r := req.Clone(req.Context())
	r.Header.Set("Cache-Control", "no-cache")
	r.Header.Set("Pragma", "no-cache")
	return n.next.RoundTrip(r)
}

func newInstallerHTTPClient() *http.Client {
	tr := http.DefaultTransport.(*http.Transport).Clone()
	return &http.Client{
		Timeout:   120 * time.Second,
		Transport: &noCacheRoundTripper{next: tr},
	}
}

func cacheBustURL(raw string) string {
	u, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	q := u.Query()
	q.Set("cb", strconv.FormatInt(time.Now().UnixNano(), 10))
	u.RawQuery = q.Encode()
	return u.String()
}

func shortSHA(hex string) string {
	if len(hex) > 16 {
		return hex[:16] + "…"
	}
	return hex
}

// effectivePayloadURL picks the download URL for the payload tarball.
// When NODEADLINE_BASE_URL is not the default production host, the manifest still lists
// https://nodeadline.online/downloads/... — we take the path and fetch from the same base
// so local `python -m http.server public/` can supply a fresh payload without deploying.
func effectivePayloadURL(base, artifactURL string) string {
	base = strings.TrimRight(strings.TrimSpace(base), "/")
	artifactURL = strings.TrimSpace(artifactURL)
	if artifactURL == "" {
		return base + "/downloads/core-node-payload.tar.gz"
	}
	if strings.EqualFold(base, strings.TrimRight(defaultBase, "/")) {
		return artifactURL
	}
	u, err := url.Parse(artifactURL)
	if err != nil {
		return artifactURL
	}
	if strings.HasPrefix(artifactURL, "/") {
		return base + artifactURL
	}
	if u.Path != "" {
		out := base + u.Path
		if u.RawQuery != "" {
			out += "?" + u.RawQuery
		}
		return out
	}
	return artifactURL
}

func main() {
	silent, noTray := parseInstallerFlags()

	home, _ := os.UserHomeDir()
	installDir := envOr("NODEADLINE_INSTALL_DIR", defaultInstallDir(home))
	runtimeDir := filepath.Join(installDir, "runtime")
	finalLog := filepath.Join(runtimeDir, "installer.log")
	logPath := finalLog
	lf, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		logPath = filepath.Join(os.TempDir(), "nodeadline-installer.log")
		lf, _ = os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	}
	if lf == nil {
		lf, _ = os.OpenFile(os.DevNull, os.O_WRONLY, 0644)
	}

	var mw io.Writer = io.MultiWriter(os.Stdout, lf)
	if silent && runtime.GOOS == "windows" {
		mw = lf
		freeConsoleIfNeeded()
	}
	log.SetOutput(mw)
	log.SetFlags(log.Ldate | log.Ltime | log.Lshortfile)
	initConsoleEarly()

	defer func() {
		if r := recover(); r != nil {
			log.Printf("PANIC: %v", r)
			waitForUserOnWindows()
			os.Exit(1)
		}
	}()

	if err := os.MkdirAll(runtimeDir, 0755); err != nil {
		fatalExitf("FATAL: cannot create %s: %v", runtimeDir, err)
	}
	if logPath != finalLog {
		lf2, err := os.OpenFile(finalLog, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
		if err == nil {
			_ = lf.Close()
			lf = lf2
			logPath = finalLog
			if silent && runtime.GOOS == "windows" {
				mw = lf
			} else {
				mw = io.MultiWriter(os.Stdout, lf)
			}
			log.SetOutput(mw)
		}
	}

	if envOr("NODEADLINE_SELF_UPGRADE", "") != "" {
		log.Printf("self-upgrade relaunch")
	}
	logInfof("nodeadline installer start os=%s/%s installDir=%s log=%s",
		runtime.GOOS, runtime.GOARCH, installDir, logPath)

	useTray := runtime.GOOS == "windows" && silent && !noTray

	shutdown := make(chan struct{})
	var shutdownOnce sync.Once
	triggerShutdown := func() {
		shutdownOnce.Do(func() { close(shutdown) })
	}

	go registerSignalHandler(triggerShutdown)

	if useTray {
		installerDone := make(chan struct{})
		go func() {
			_ = runInstallerCore(shutdown, mw)
			close(installerDone)
		}()
		runWindowsTray(mw, shutdown, triggerShutdown, installerDone)
		os.Exit(0)
	}

	_ = runInstallerCore(shutdown, mw)
	os.Exit(0)
}

func registerSignalHandler(triggerShutdown func()) {
	sig := make(chan os.Signal, 2)
	if runtime.GOOS == "windows" {
		signal.Notify(sig, os.Interrupt)
	} else {
		signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	}
	go func() {
		<-sig
		triggerShutdown()
	}()
}

func buildNodeCmd(venvPy, nodeMain, appDir, runtimeDir string, port int, base string, mw io.Writer) *exec.Cmd {
	cmd := exec.Command(venvPy, "-u", nodeMain)
	cmd.Dir = appDir
	cmd.Env = append(os.Environ(),
		"PORT="+strconv.Itoa(port),
		"NODEADLINE_RUNTIME_DIR="+runtimeDir,
		"NODEADLINE_BASE_URL="+base,
		"PYTHONUNBUFFERED=1",
	)
	cmd.Stdout = mw
	cmd.Stderr = mw
	return cmd
}

func waitForUserOnWindows() {
	if runtime.GOOS != "windows" {
		return
	}
	if installerSilent {
		return
	}
	log.Println("Waiting 90s so you can read errors / copy log path. Close window to exit sooner.")
	time.Sleep(90 * time.Second)
}

// fatalExitf replaces log.Fatal/log.Fatalf: those call os.Exit and skip defer + wait on Windows.
func fatalExitf(format string, args ...interface{}) {
	if len(args) == 0 {
		log.Print(format)
	} else {
		log.Printf(format, args...)
	}
	waitForUserOnWindows()
	os.Exit(1)
}

func defaultInstallDir(home string) string {
	if runtime.GOOS == "windows" {
		l := os.Getenv("LOCALAPPDATA")
		if l != "" {
			return filepath.Join(l, "nodeadline-v2")
		}
	}
	return filepath.Join(home, ".local", "share", "nodeadline-v2")
}

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func readPreferredPort(runtimeDir string) int {
	p := filepath.Join(runtimeDir, "runtime_state.json")
	b, err := os.ReadFile(p)
	if err != nil {
		return 0
	}
	var v struct {
		ListenPort int `json:"listen_port"`
	}
	if json.Unmarshal(b, &v) != nil {
		return 0
	}
	return v.ListenPort
}

// listenCandidatePorts returns preferred port first (from runtime_state.json), then defaults.
func listenCandidatePorts(runtimeDir string) []int {
	candidates := []int{28473, 37651, 45123, 52891, 7332}
	if pref := readPreferredPort(runtimeDir); pref > 0 {
		seen := map[int]bool{pref: true}
		out := []int{pref}
		for _, c := range candidates {
			if !seen[c] {
				seen[c] = true
				out = append(out, c)
			}
		}
		return out
	}
	return candidates
}

// killExistingNodeListeners stops any leftover node (waitress) from a prior run so only one
// web server binds our ports and reinstall can replace files safely.
func killExistingNodeListeners(runtimeDir string) {
	logInfof("kill listeners on known node ports (cleanup previous node)")
	for _, p := range listenCandidatePorts(runtimeDir) {
		killListenersOnPort(p)
	}
}

func stopBeforePayloadReplace(runner *nodeRunner, runtimeDir string) {
	if runner != nil {
		runner.StopNode()
	}
	killExistingNodeListeners(runtimeDir)
}

func pickListenPort(runtimeDir string) int {
	if p := os.Getenv("NODEADLINE_LOCAL_PORT"); p != "" {
		if n, err := strconv.Atoi(p); err == nil {
			killListenersOnPort(n)
			time.Sleep(200 * time.Millisecond)
			if canBind(n) {
				return n
			}
		}
	}
	for _, p := range listenCandidatePorts(runtimeDir) {
		killListenersOnPort(p)
		time.Sleep(200 * time.Millisecond)
		if canBind(p) {
			return p
		}
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		fatalExitf("no free port: %v", err)
	}
	defer ln.Close()
	return ln.Addr().(*net.TCPAddr).Port
}

func canBind(port int) bool {
	ln, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port))
	if err != nil {
		return false
	}
	ln.Close()
	return true
}

func writePortFile(runtimeDir string, port int) {
	_ = os.MkdirAll(runtimeDir, 0755)
	p := filepath.Join(runtimeDir, "runtime_state.json")
	j := fmt.Sprintf("{\n  \"listen_host\": \"127.0.0.1\",\n  \"listen_port\": %d\n}\n", port)
	_ = os.WriteFile(p, []byte(j), 0644)
}

func ensureVenv(installDir, runtimeDir string) string {
	dir := filepath.Join(installDir, "runtime", "venv")
	var exe string
	if runtime.GOOS == "windows" {
		exe = filepath.Join(dir, "Scripts", "python.exe")
	} else {
		exe = filepath.Join(dir, "bin", "python3")
	}
	if _, err := os.Stat(exe); err == nil {
		return exe
	}
	py, kind := findSystemPython()
	if py == "" {
		fatalExitf("Python not found. Install Python 3.10+ from python.org and tick 'Add to PATH', or install the 'py' launcher.")
	}
	logInfof("creating venv with %s (%s)", py, kind)
	_ = os.RemoveAll(dir)
	var c *exec.Cmd
	if kind == "py" {
		c = exec.Command(py, "-3", "-m", "venv", dir)
	} else {
		c = exec.Command(py, "-m", "venv", dir)
	}
	c.Stdout = log.Writer()
	c.Stderr = log.Writer()
	if err := c.Run(); err != nil {
		fatalExitf("venv failed: %v", err)
	}
	if _, err := os.Stat(exe); err != nil {
		fatalExitf("venv created but missing %s: %v", exe, err)
	}
	return exe
}

// findSystemPython returns path and kind: "py" | "python"
func findSystemPython() (string, string) {
	if runtime.GOOS == "windows" {
		// Windows Store stub / order matters
		if p, err := exec.LookPath("py"); err == nil {
			return p, "py"
		}
		if p, err := exec.LookPath("python"); err == nil {
			return p, "python"
		}
		if p, err := exec.LookPath("python3"); err == nil {
			return p, "python"
		}
		return "", ""
	}
	for _, n := range []string{"python3", "python"} {
		if p, err := exec.LookPath(n); err == nil {
			return p, "python"
		}
	}
	return "", ""
}

func writePublishedVersion(runtimeDir, version string) {
	version = strings.TrimSpace(version)
	if version == "" {
		version = "2.0.0-dev"
	}
	_ = os.MkdirAll(runtimeDir, 0755)
	p := filepath.Join(runtimeDir, "published_version.txt")
	_ = os.WriteFile(p, []byte(version+"\n"), 0644)
}

func syncPayload(client *http.Client, base, installDir, appDir, venvPy string, runner *nodeRunner) (string, bool, error) {
	verURL := cacheBustURL(base + "/version.json")
	b, err := fetch(client, verURL)
	if err != nil {
		return "", false, err
	}
	var v struct {
		Version        string `json:"version"`
		ManifestURL    string `json:"manifest_url"`
		Requirements   string `json:"requirements_mirror"`
		InstallerBuild string `json:"installer_build"`
	}
	_ = json.Unmarshal(b, &v)
	installerBuild := strings.TrimSpace(v.InstallerBuild)
	runtimeDir := filepath.Join(installDir, "runtime")
	writePublishedVersion(runtimeDir, v.Version)
	manURL := v.ManifestURL
	if manURL == "" {
		manURL = base + "/downloads/core-manifest.json"
	}
	manURL = cacheBustURL(manURL)
	mb, err := fetch(client, manURL)
	if err != nil {
		return "", false, err
	}
	var man struct {
		Version   string `json:"version"`
		Artifacts []struct {
			URL    string `json:"url"`
			SHA256 string `json:"sha256"`
			Size   int64  `json:"size"`
		} `json:"artifacts"`
	}
	if err := json.Unmarshal(mb, &man); err != nil {
		return "", false, err
	}
	if len(man.Artifacts) == 0 {
		return "", false, fmt.Errorf("empty manifest")
	}
	a := man.Artifacts[0]
	marker := filepath.Join(runtimeDir, "last_payload_sha256.txt")
	if envOr("NODEADLINE_FORCE_PAYLOAD_SYNC", "") != "" {
		if err := os.Remove(marker); err != nil && !os.IsNotExist(err) {
			log.Printf("payload sync: cannot remove marker %s: %v", marker, err)
		} else {
			log.Printf("payload sync: NODEADLINE_FORCE_PAYLOAD_SYNC set — will re-download payload")
		}
	}
	prevB, _ := os.ReadFile(marker)
	prevS := strings.TrimSpace(string(prevB))
	if a.SHA256 != "" && strings.EqualFold(prevS, a.SHA256) {
		if _, err := os.Stat(filepath.Join(appDir, "node_main.py")); err == nil {
			now := time.Now()
			if now.Sub(lastPayloadIdleLog) >= 5*time.Minute {
				log.Printf("payload sync: up to date (sha %s)", shortSHA(a.SHA256))
				lastPayloadIdleLog = now
			}
			return installerBuild, false, nil
		}
	}
	stopBeforePayloadReplace(runner, runtimeDir)
	payloadURL := effectivePayloadURL(base, a.URL)
	log.Printf("payload sync: downloading new payload (want sha %s) from %s", shortSHA(a.SHA256), payloadURL)
	staging := filepath.Join(installDir, "staging", "core-node-payload.tar.gz")
	if err := downloadFile(client, cacheBustURL(payloadURL), staging); err != nil {
		return "", false, err
	}
	if ok, g := sha256file(staging); !ok || !strings.EqualFold(g, a.SHA256) {
		return "", false, fmt.Errorf("sha256 mismatch (got %s want %s)", g, a.SHA256)
	}
	_ = os.RemoveAll(appDir)
	_ = os.MkdirAll(appDir, 0755)
	if err := extractTarGz(staging, appDir); err != nil {
		return "", false, err
	}
	req := filepath.Join(appDir, "requirements-node.txt")
	mirror := strings.TrimRight(v.Requirements, "/")
	if mirror == "" {
		mirror = strings.TrimRight(base+"/Nodeadline/Core/requirements", "/")
	}
	pipCfg, werr := writePipConfig(filepath.Join(installDir, "runtime"))
	if werr != nil {
		log.Printf("pip config file: %v", werr)
	}
	pip := venvPy
	// Do not run `pip install --upgrade pip` — it always probes pypi.org/simple/pip/ even when pip
	// is already satisfied, and urllib3 often keeps the 15s socket timeout despite CLI flags.
	// The venv's embedded pip is enough; only install project requirements.
	//
	// --find-links alone still uses PyPI as the primary index; our mirror must be used with
	// --no-index so installs work when pypi.org is blocked or resets connections.
	install := []string{
		"-m", "pip", "install",
		"--retries", "10", "--timeout", "300",
	}
	if strings.HasPrefix(mirror, "http") {
		install = append(install, "--no-index", "--find-links", mirror)
	}
	install = append(install, "-r", req)
	c := exec.Command(pip, install...)
	c.Env = pipEnv(pipCfg)
	c.Stdout = log.Writer()
	c.Stderr = log.Writer()
	if err := c.Run(); err != nil {
		return "", false, fmt.Errorf("pip %v: %w", install, err)
	}
	_ = os.WriteFile(marker, []byte(strings.ToLower(a.SHA256)), 0644)
	logOKf("payload sync: extracted + pip ok — node will restart via supervisor")
	return installerBuild, true, nil
}

func writePipConfig(runtimeDir string) (string, error) {
	if err := os.MkdirAll(runtimeDir, 0755); err != nil {
		return "", err
	}
	p := filepath.Join(runtimeDir, "pip.ini")
	cfg := "[global]\ntimeout = 300\nretries = 10\n"
	if err := os.WriteFile(p, []byte(cfg), 0644); err != nil {
		return "", err
	}
	return filepath.Abs(p)
}

func pipEnv(pipCfg string) []string {
	e := append(os.Environ(),
		"PIP_DEFAULT_TIMEOUT=300",
		"PIP_DISABLE_PIP_VERSION_CHECK=1",
	)
	if pipCfg != "" {
		e = append(e, "PIP_CONFIG_FILE="+pipCfg)
	}
	return e
}

func fetch(c *http.Client, url string) ([]byte, error) {
	resp, err := c.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("HTTP %d %s", resp.StatusCode, url)
	}
	return io.ReadAll(resp.Body)
}

func downloadFile(c *http.Client, url, dest string) error {
	dir := filepath.Dir(dest)
	_ = os.MkdirAll(dir, 0755)
	f, err := os.CreateTemp(dir, "installer-next-*.part")
	if err != nil {
		return err
	}
	partPath := f.Name()
	resp, err := c.Get(url)
	if err != nil {
		_ = f.Close()
		_ = os.Remove(partPath)
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		_ = f.Close()
		_ = os.Remove(partPath)
		return fmt.Errorf("HTTP %d %s", resp.StatusCode, url)
	}
	_, err = io.Copy(f, resp.Body)
	cerr := f.Close()
	if err != nil {
		_ = os.Remove(partPath)
		return err
	}
	if cerr != nil {
		_ = os.Remove(partPath)
		return cerr
	}
	_ = os.Remove(dest)
	if err := os.Rename(partPath, dest); err != nil {
		_ = os.Remove(partPath)
		return err
	}
	return nil
}

func sha256file(path string) (bool, string) {
	f, err := os.Open(path)
	if err != nil {
		return false, ""
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return false, ""
	}
	return true, hex.EncodeToString(h.Sum(nil))
}

func extractTarGz(src, dest string) error {
	f, err := os.Open(src)
	if err != nil {
		return err
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		return err
	}
	defer gz.Close()
	tr := tar.NewReader(gz)
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
		name := hdr.Name
		if name == "." || name == "./" {
			continue
		}
		name = strings.TrimPrefix(name, "./")
		if strings.Contains(name, "..") {
			continue
		}
		target := filepath.Join(dest, filepath.FromSlash(name))
		if hdr.Typeflag == tar.TypeDir {
			_ = os.MkdirAll(target, 0755)
			continue
		}
		_ = os.MkdirAll(filepath.Dir(target), 0755)
		mode := os.FileMode(0644)
		if hdr.Mode > 0 {
			mode = os.FileMode(hdr.Mode & 0777)
		}
		out, err := os.OpenFile(target, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, mode)
		if err != nil {
			return err
		}
		if _, err := io.Copy(out, tr); err != nil {
			out.Close()
			return err
		}
		out.Close()
	}
	return nil
}

func waitHealthy(port int) {
	url := fmt.Sprintf("http://127.0.0.1:%d/health", port)
	c := &http.Client{Timeout: 3 * time.Second, Transport: &http.Transport{Proxy: nil}}
	dead := time.Now().Add(120 * time.Second)
	for time.Now().Before(dead) {
		resp, err := c.Get(url)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == 200 {
				logOKf("node healthy")
				return
			}
		}
		time.Sleep(2 * time.Second)
	}
	logWarnf("health timeout (continuing)")
}

func updateLoop(
	base, installDir, appDir, venvPy string,
	runner *nodeRunner,
	port int,
	nodeMain string,
	mw io.Writer,
	runtimeDir string,
	httpClient *http.Client,
) {
	t := time.NewTicker(tickEvery)
	for range t.C {
		tryInstallerUpgrade(httpClient, base, installDir, runtimeDir, runner, port, runner.Get() != nil)
		ib, replaced, err := syncPayload(httpClient, base, installDir, appDir, venvPy, runner)
		if err != nil {
			logWarnf("background sync: %v", err)
			continue
		}
		if ib != "" {
			writeLocalBuild(runtimeDir, ib)
		}
		if replaced {
			logInfof("payload changed on server — restarting node")
			runner.StopNode()
			killListenersOnPort(port)
			time.Sleep(400 * time.Millisecond)
			cmd := buildNodeCmd(venvPy, nodeMain, appDir, runtimeDir, port, base, mw)
			if err := cmd.Start(); err != nil {
				logWarnf("restart node: %v", err)
				continue
			}
			runner.setCmd(cmd)
			logOKf("node restarted pid=%d port=%d", cmd.Process.Pid, port)
			waitHealthy(port)
		}
	}
}
