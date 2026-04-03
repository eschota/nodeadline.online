package main

import "os"

// installerSilent: no console on Windows; waitForUserOnWindows skips delay.
var installerSilent bool

func parseInstallerFlags() (silent, noTray bool) {
	for _, a := range os.Args[1:] {
		switch a {
		case "-silent", "--silent":
			silent = true
		case "-no-tray", "--no-tray":
			noTray = true
		}
	}
	if os.Getenv("NODEADLINE_SILENT") == "1" {
		silent = true
	}
	if os.Getenv("NODEADLINE_NO_TRAY") == "1" {
		noTray = true
	}
	installerSilent = silent
	return silent, noTray
}
