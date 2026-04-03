package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
)

var (
	trayMu         sync.RWMutex
	trayRuntimeDir string
	restartFlag    int32 // set from tray: relaunch exe after installer core stops
)

func setTrayRuntimeDir(d string) {
	trayMu.Lock()
	trayRuntimeDir = d
	trayMu.Unlock()
}

func getTrayRuntimeDir() string {
	trayMu.RLock()
	defer trayMu.RUnlock()
	return trayRuntimeDir
}

// cabinetDashboardURL returns local dashboard URL (/site/) using runtime_state.json port.
func cabinetDashboardURL() string {
	rd := getTrayRuntimeDir()
	if rd == "" {
		return "http://127.0.0.1:37651/site/"
	}
	port := readPreferredPort(rd)
	if port <= 0 {
		return "http://127.0.0.1:37651/site/"
	}
	return fmt.Sprintf("http://127.0.0.1:%d/site/", port)
}

// installerLogPath is runtime/installer.log (same file the installer writes to).
func installerLogPath() string {
	rd := getTrayRuntimeDir()
	if rd != "" {
		return filepath.Join(rd, "installer.log")
	}
	l := os.Getenv("LOCALAPPDATA")
	if l == "" {
		return ""
	}
	return filepath.Join(l, "nodeadline-v2", "runtime", "installer.log")
}

func markTrayRestart() {
	atomic.StoreInt32(&restartFlag, 1)
}

func takeTrayRestart() bool {
	return atomic.SwapInt32(&restartFlag, 0) != 0
}
