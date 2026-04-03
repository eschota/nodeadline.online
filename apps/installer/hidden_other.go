//go:build !windows

package main

func freeConsoleIfNeeded() {}

func openLocalURL(url string) {}
