package main

import (
	"fmt"
	"log"
	"os"
)

var (
	coReset  = ""
	coBold   = ""
	coDim    = ""
	coRed    = ""
	coGreen  = ""
	coYellow = ""
	coCyan   = ""
	coGray   = ""
)

// initConsoleEarly enables ANSI on Windows (VT) and sets color codes unless NO_COLOR / NODEADLINE_NO_COLOR.
func initConsoleEarly() {
	if os.Getenv("NODEADLINE_NO_COLOR") != "" || os.Getenv("NO_COLOR") != "" {
		return
	}
	enableVTIfWindows()
	coReset = "\033[0m"
	coBold = "\033[1m"
	coDim = "\033[2m"
	coRed = "\033[31m"
	coGreen = "\033[32m"
	coYellow = "\033[33m"
	coCyan = "\033[36m"
	coGray = "\033[90m"
}

func logInfof(format string, args ...interface{}) {
	log.Printf("%s[INFO]%s %s%s", coCyan, coReset, fmt.Sprintf(format, args...), coReset)
}

func logOKf(format string, args ...interface{}) {
	log.Printf("%s[OK]%s %s%s", coGreen, coReset, fmt.Sprintf(format, args...), coReset)
}

func logWarnf(format string, args ...interface{}) {
	log.Printf("%s[WARN]%s %s%s", coYellow, coReset, fmt.Sprintf(format, args...), coReset)
}

// logCautionf prints a red CAUTION line (unexpected node exit / serious but recoverable).
func logCautionf(format string, args ...interface{}) {
	msg := fmt.Sprintf(format, args...)
	log.Printf("%s%sCAUTION%s — %s%s%s", coBold, coRed, coReset, coRed, msg, coReset)
}

func logErrf(format string, args ...interface{}) {
	log.Printf("%s[ERROR]%s %s%s", coRed, coReset, fmt.Sprintf(format, args...), coReset)
}
