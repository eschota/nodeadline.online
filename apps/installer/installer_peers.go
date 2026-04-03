package main

import (
	"encoding/csv"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
)

// killOtherInstallerInstances stops other processes running the same installer binary
// (same executable file name). The current PID is never killed so a new run replaces
// duplicate windows/listeners instead of stacking them.
func killOtherInstallerInstances() {
	if os.Getenv("NODEADLINE_SKIP_PEER_KILL") != "" {
		log.Printf("skip duplicate installer cleanup (restart child)")
		return
	}
	self := os.Getpid()
	exe, err := os.Executable()
	if err != nil {
		return
	}
	base := filepath.Base(exe)
	switch runtime.GOOS {
	case "windows":
		killOtherWindowsInstaller(base, self)
	default:
		killOtherUnixInstaller(base, self)
	}
}

func killOtherWindowsInstaller(baseExe string, self int) {
	names := []string{baseExe, "nodeadline-installer-next.exe"}
	seen := map[int]bool{self: true}
	for _, image := range names {
		out, err := exec.Command("cmd", "/c", "tasklist", "/FI", fmt.Sprintf("IMAGENAME eq %s", image), "/FO", "CSV", "/NH").Output()
		if err != nil {
			log.Printf("stale installer cleanup: tasklist %s: %v", image, err)
			continue
		}
		text := strings.TrimSpace(string(out))
		if text == "" || strings.Contains(strings.ToLower(text), "no tasks") {
			continue
		}
		for _, line := range strings.Split(text, "\n") {
			line = strings.TrimSpace(line)
			if line == "" {
				continue
			}
			r := csv.NewReader(strings.NewReader(line))
			r.LazyQuotes = true
			rec, err := r.Read()
			if err != nil || len(rec) < 2 {
				continue
			}
			pid, err := strconv.Atoi(strings.TrimSpace(rec[1]))
			if err != nil || pid <= 0 || seen[pid] {
				continue
			}
			seen[pid] = true
			log.Printf("kill stale installer pid=%d image=%s (duplicate instance)", pid, image)
			_ = exec.Command("taskkill", "/PID", strconv.Itoa(pid), "/F").Run()
		}
	}
}

func killOtherUnixInstaller(base string, self int) {
	// -f matches argv; exclude self PID so we never signal this process.
	out, err := exec.Command("pgrep", "-f", base).Output()
	if err != nil {
		return
	}
	for _, field := range strings.Fields(string(out)) {
		pid, err := strconv.Atoi(strings.TrimSpace(field))
		if err != nil || pid <= 0 || pid == self {
			continue
		}
		log.Printf("kill stale installer pid=%d (duplicate instance)", pid)
		_ = exec.Command("kill", "-9", strconv.Itoa(pid)).Run()
	}
}
