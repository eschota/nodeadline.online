package main

import (
	"os/exec"
	"sync"
	"sync/atomic"
)

// intentionalNodeStop: supervisor must not treat exit as crash (payload sync, installer upgrade, shutdown).
var intentionalNodeStop int32

func takeIntentionalNodeStop() bool {
	return atomic.SwapInt32(&intentionalNodeStop, 0) != 0
}

// nodeRunner holds the supervised Python node process; used for shutdown, installer upgrade, and payload restarts.
type nodeRunner struct {
	mu  sync.Mutex
	cmd *exec.Cmd
}

func (r *nodeRunner) Get() *exec.Cmd {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.cmd
}

func (r *nodeRunner) setCmd(c *exec.Cmd) {
	r.mu.Lock()
	r.cmd = c
	r.mu.Unlock()
}

// clearCmdIfSame clears runner.cmd only if it still points to the same *exec.Cmd (after Wait returned once).
func (r *nodeRunner) clearCmdIfSame(c *exec.Cmd) {
	if c == nil {
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.cmd == c {
		r.cmd = nil
	}
}

// StopNode requests an intentional stop: Kill only — Wait runs in superviseNode (single Wait per process).
func (r *nodeRunner) StopNode() {
	r.mu.Lock()
	defer r.mu.Unlock()
	atomic.StoreInt32(&intentionalNodeStop, 1)
	if r.cmd != nil && r.cmd.Process != nil {
		logInfof("stopping node pid=%d", r.cmd.Process.Pid)
		_ = r.cmd.Process.Kill()
	}
	r.cmd = nil
}
