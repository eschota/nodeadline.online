//go:build windows

package main

import (
	"os"
	"os/exec"
	"syscall"
)

func freeConsoleIfNeeded() {
	// Detach from console so -silent has no black window; logging uses file only.
	k32 := syscall.NewLazyDLL("kernel32.dll")
	pFreeConsole := k32.NewProc("FreeConsole")
	pFreeConsole.Call()
}

func openLocalURL(url string) {
	if url == "" {
		return
	}
	_ = exec.Command("cmd", "/c", "start", "", url).Start()
}

func openInstallerLog() {
	p := installerLogPath()
	if p == "" {
		return
	}
	if _, err := os.Stat(p); os.IsNotExist(err) {
		_ = os.WriteFile(p, []byte{}, 0644)
	}
	_ = exec.Command("notepad.exe", p).Start()
}
