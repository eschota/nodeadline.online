//go:build !windows

package main

func ensureStartMenuShortcut(_ string) error {
	return nil
}
