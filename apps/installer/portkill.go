package main

import (
	"context"
	"fmt"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// killListenersOnPort terminates processes listening on TCP port (IPv4).
// Used so a single node instance can bind the preferred port during dev/debug.
func killListenersOnPort(port int) {
	if port <= 0 || port > 65535 {
		return
	}
	switch runtime.GOOS {
	case "windows":
		killListenersWindows(port)
	case "darwin":
		killListenersDarwin(port)
	default:
		killListenersUnix(port)
	}
	time.Sleep(400 * time.Millisecond)
}

// killListenersWindows uses netstat + taskkill only.
// PowerShell Get-NetTCPConnection has been observed to hang for a long time on some Windows systems.
func killListenersWindows(port int) {
	suffix := fmt.Sprintf(":%d", port)
	ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, "cmd", "/c", "netstat", "-ano").Output()
	if err != nil {
		return
	}
	seen := map[int]bool{}
	for _, line := range strings.Split(string(out), "\n") {
		line = strings.TrimSpace(strings.TrimRight(line, "\r"))
		if !strings.Contains(line, "LISTENING") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 5 {
			continue
		}
		addr := fields[1]
		if !strings.HasSuffix(addr, suffix) {
			continue
		}
		pidStr := fields[len(fields)-1]
		pid, err := strconv.Atoi(pidStr)
		if err != nil || pid <= 0 || seen[pid] {
			continue
		}
		seen[pid] = true
		_ = exec.Command("taskkill", "/PID", pidStr, "/F").Run()
	}
}

func killListenersDarwin(port int) {
	out, err := exec.Command("lsof", "-nP", fmt.Sprintf("-iTCP:%d", port), "-sTCP:LISTEN", "-t").Output()
	if err != nil {
		return
	}
	for _, s := range strings.Fields(string(out)) {
		pid, err := strconv.Atoi(strings.TrimSpace(s))
		if err != nil || pid <= 0 {
			continue
		}
		_ = exec.Command("kill", "-9", strconv.Itoa(pid)).Run()
	}
}

func killListenersUnix(port int) {
	// fuser -k is common on Linux; ignore errors
	_ = exec.Command("fuser", "-k", fmt.Sprintf("%d/tcp", port)).Run()
}
