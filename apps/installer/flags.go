package main

import (
	"os"
	"runtime"
)

// installerSilent: no console on Windows; waitForUserOnWindows skips delay.
var installerSilent bool

func parseInstallerFlags() (silent, noTray bool) {
	var hasConsole, hasSilent bool
	for _, a := range os.Args[1:] {
		switch a {
		case "-silent", "--silent":
			hasSilent = true
		case "-console", "--console", "-no-silent", "--no-silent":
			hasConsole = true
		case "-no-tray", "--no-tray":
			noTray = true
		}
	}
	if os.Getenv("NODEADLINE_NO_TRAY") == "1" {
		noTray = true
	}

	silent = false
	if runtime.GOOS == "windows" {
		silent = true
	}
	if hasConsole {
		silent = false
	}
	if hasSilent {
		silent = true
	}
	if os.Getenv("NODEADLINE_CONSOLE") == "1" {
		silent = false
	}
	if os.Getenv("NODEADLINE_SILENT") == "1" {
		silent = true
	}
	installerSilent = silent
	return silent, noTray
}
