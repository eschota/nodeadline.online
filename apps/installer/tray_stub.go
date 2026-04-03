//go:build !windows

package main

import "io"

func runWindowsTray(_ io.Writer, _ chan struct{}, _ func(), _ <-chan struct{}) {
	// unreachable: main never calls this on non-Windows
}
