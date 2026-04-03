//go:build windows

package main

import (
	"syscall"
)

const enableVirtualTerminalProcessing = 0x0004

func enableVTIfWindows() {
	h, err := syscall.GetStdHandle(syscall.STD_OUTPUT_HANDLE)
	if err != nil || h == syscall.InvalidHandle {
		return
	}
	var mode uint32
	if err := syscall.GetConsoleMode(h, &mode); err != nil {
		return
	}
	mode |= enableVirtualTerminalProcessing
	p := syscall.NewLazyDLL("kernel32.dll").NewProc("SetConsoleMode")
	p.Call(uintptr(h), uintptr(mode))
}
