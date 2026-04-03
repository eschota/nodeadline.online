//go:build windows

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// ensureStartMenuShortcut creates %APPDATA%\Microsoft\Windows\Start Menu\Programs\Nodeadline\Nodeadline.lnk
// pointing at exePath with arguments "-silent". Uses PowerShell + WScript.Shell (no extra Go deps).
func ensureStartMenuShortcut(exePath string) error {
	appData := os.Getenv("APPDATA")
	if appData == "" {
		return fmt.Errorf("APPDATA is empty")
	}
	dir := filepath.Join(appData, "Microsoft", "Windows", "Start Menu", "Programs", "Nodeadline")
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("mkdir programs folder: %w", err)
	}
	lnk := filepath.Join(dir, "Nodeadline.lnk")

	cmd := exec.Command(
		"powershell.exe",
		"-NoProfile",
		"-NonInteractive",
		"-ExecutionPolicy", "Bypass",
		"-Command",
		"$ws = New-Object -ComObject WScript.Shell; "+
			"$s = $ws.CreateShortcut($env:NODEADLINE_SM_LNK); "+
			"$s.TargetPath = $env:NODEADLINE_SM_EXE; "+
			"$s.Arguments = '-silent'; "+
			"$s.Save()",
	)
	cmd.Env = append(os.Environ(),
		"NODEADLINE_SM_LNK="+lnk,
		"NODEADLINE_SM_EXE="+exePath,
	)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w: %s", err, string(out))
	}
	return nil
}
