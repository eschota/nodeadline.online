//go:build windows

package main

import (
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
