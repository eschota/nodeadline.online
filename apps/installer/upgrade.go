package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
)

var installerUpgradeMu sync.Mutex

type versionMeta struct {
	Version        string `json:"version"`
	InstallerBuild string `json:"installer_build"`
	URL            string `json:"url"`
	LinuxURL       string `json:"linux_url"`
	DarwinURL      string `json:"darwin_url"`
}

func fetchVersionMeta(client *http.Client, base string) (*versionMeta, error) {
	b, err := fetch(client, cacheBustURL(strings.TrimRight(base, "/")+"/version.json"))
	if err != nil {
		return nil, err
	}
	var m versionMeta
	if err := json.Unmarshal(b, &m); err != nil {
		return nil, err
	}
	return &m, nil
}

func parseBuild(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0
	}
	return n
}

func readLocalBuild(runtimeDir string) int {
	p := filepath.Join(runtimeDir, "installer_build.txt")
	b, err := os.ReadFile(p)
	if err != nil {
		return 0
	}
	return parseBuild(string(b))
}

func writeLocalBuild(runtimeDir, build string) {
	_ = os.MkdirAll(runtimeDir, 0755)
	p := filepath.Join(runtimeDir, "installer_build.txt")
	_ = os.WriteFile(p, []byte(strings.TrimSpace(build)+"\n"), 0644)
}

func installerURLForPlatform(m *versionMeta) string {
	if m == nil {
		return ""
	}
	switch {
	case runtime.GOOS == "windows" && strings.Contains(runtime.GOARCH, "64"):
		return m.URL
	case runtime.GOOS == "linux" && runtime.GOARCH == "amd64":
		return m.LinuxURL
	case runtime.GOOS == "darwin" && runtime.GOARCH == "arm64":
		return m.DarwinURL
	case runtime.GOOS == "darwin":
		return m.DarwinURL
	default:
		return m.LinuxURL
	}
}

// versionForFilename strips prerelease suffix (e.g. 2.0.6-rc1 -> 2.0.6) for use in artifact names.
func versionForFilename(v string) string {
	v = strings.TrimSpace(v)
	if i := strings.Index(v, "-"); i >= 0 {
		v = strings.TrimSpace(v[:i])
	}
	return strings.ReplaceAll(v, "/", "-")
}

// installerArtifactName is the basename used in public/downloads/SHA256SUMS (must match published files).
func installerArtifactName(meta *versionMeta) string {
	v := ""
	if meta != nil {
		v = versionForFilename(meta.Version)
	}
	if v == "" {
		v = "0.0.0"
	}
	switch {
	case runtime.GOOS == "windows" && strings.Contains(runtime.GOARCH, "64"):
		return fmt.Sprintf("nodeadline-installer-windows-amd64-v%s.exe", v)
	case runtime.GOOS == "linux" && runtime.GOARCH == "amd64":
		return fmt.Sprintf("nodeadline-installer-linux-amd64-v%s", v)
	case runtime.GOOS == "darwin" && runtime.GOARCH == "arm64":
		return fmt.Sprintf("nodeadline-installer-darwin-arm64-v%s", v)
	case runtime.GOOS == "darwin":
		return fmt.Sprintf("nodeadline-installer-darwin-arm64-v%s", v)
	default:
		return fmt.Sprintf("nodeadline-installer-linux-amd64-v%s", v)
	}
}

func installerStagingPath(installDir string) string {
	if runtime.GOOS == "windows" {
		return filepath.Join(installDir, "staging", "nodeadline-installer-next.exe")
	}
	return filepath.Join(installDir, "staging", "nodeadline-installer-next")
}

func sha256FromSUMS(sums, baseName string) string {
	for _, line := range strings.Split(sums, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		if !strings.Contains(line, baseName) {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) >= 1 && len(fields[0]) == 64 {
			return fields[0]
		}
	}
	return ""
}

func fetchSHA256SUMS(client *http.Client, base string) (string, error) {
	b, err := fetch(client, cacheBustURL(strings.TrimRight(base, "/")+"/downloads/SHA256SUMS"))
	if err != nil {
		return "", err
	}
	return string(b), nil
}

// tryInstallerUpgrade downloads a newer installer from version.json when installer_build
// increased on the server, verifies SHA256SUMS, then relaunches and exits the current process.
func tryInstallerUpgrade(
	client *http.Client,
	base, installDir, runtimeDir string,
	runner *nodeRunner,
	port int,
	nodeStarted bool,
) {
	installerUpgradeMu.Lock()
	defer installerUpgradeMu.Unlock()

	meta, err := fetchVersionMeta(client, base)
	if err != nil {
		log.Printf("installer upgrade: version.json: %v", err)
		return
	}
	remote := parseBuild(meta.InstallerBuild)
	local := readLocalBuild(runtimeDir)
	if remote <= local {
		return
	}
	url := installerURLForPlatform(meta)
	if url == "" {
		log.Printf("installer upgrade: no URL for this platform")
		return
	}
	sums, err := fetchSHA256SUMS(client, base)
	if err != nil {
		log.Printf("installer upgrade: SHA256SUMS: %v", err)
		return
	}
	art := installerArtifactName(meta)
	want := sha256FromSUMS(sums, art)
	if want == "" {
		log.Printf("installer upgrade: no hash line for %s", art)
		return
	}
	dest := installerStagingPath(installDir)
	_ = os.MkdirAll(filepath.Dir(dest), 0755)
	if err := downloadFile(client, cacheBustURL(url), dest); err != nil {
		log.Printf("installer upgrade: download: %v", err)
		return
	}
	if ok, g := sha256file(dest); !ok || !strings.EqualFold(g, want) {
		log.Printf("installer upgrade: sha256 mismatch want %s got %s", want, g)
		_ = os.Remove(dest)
		return
	}
	if runtime.GOOS != "windows" {
		_ = os.Chmod(dest, 0755)
	}
	writeLocalBuild(runtimeDir, meta.InstallerBuild)

	if nodeStarted && runner != nil {
		runner.StopNode()
	}
	killListenersOnPort(port)

	cmd := exec.Command(dest)
	cmd.Env = append(os.Environ(),
		"NODEADLINE_INSTALL_DIR="+installDir,
		"NODEADLINE_BASE_URL="+base,
		"NODEADLINE_SELF_UPGRADE=1",
	)
	if port > 0 {
		cmd.Env = append(cmd.Env, fmt.Sprintf("NODEADLINE_LOCAL_PORT=%d", port))
	}
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Stdin = os.Stdin
	if err := cmd.Start(); err != nil {
		log.Printf("installer upgrade: start new binary: %v", err)
		return
	}
	log.Printf("installer upgrade: launched build %s pid=%d — exiting", meta.InstallerBuild, cmd.Process.Pid)
	os.Exit(0)
}
