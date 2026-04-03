package main

import (
	"os/exec"
	"time"
)

const nodeRestartDelay = 2 * time.Minute

// superviseNode waits on the current node process; on unexpected exit logs CAUTION, waits 2 minutes, restarts.
// Intentional stops (StopNode: payload sync, shutdown) skip CAUTION and delay via intentionalNodeStop.
func superviseNode(
	runner *nodeRunner,
	buildFn func() *exec.Cmd,
	port int,
	shutdown <-chan struct{},
) {
	for {
		select {
		case <-shutdown:
			return
		default:
		}

		cmd := runner.Get()
		if cmd == nil {
			select {
			case <-shutdown:
				return
			case <-time.After(50 * time.Millisecond):
			}
			continue
		}

		errCh := make(chan error, 1)
		go func(c *exec.Cmd) {
			errCh <- c.Wait()
		}(cmd)

		var waitErr error
		select {
		case <-shutdown:
			return
		case waitErr = <-errCh:
		}
		// exec.Cmd allows only one Wait(); drop dead cmd so we never call Wait on it again (do not clear if another goroutine already set a new cmd).
		runner.clearCmdIfSame(cmd)

		select {
		case <-shutdown:
			return
		default:
		}

		if takeIntentionalNodeStop() {
			continue
		}

		if waitErr != nil {
			logCautionf("node process exited unexpectedly: %v", waitErr)
		} else {
			logCautionf("node process exited unexpectedly (code 0)")
		}

		select {
		case <-shutdown:
			return
		case <-time.After(nodeRestartDelay):
		}

		select {
		case <-shutdown:
			return
		default:
		}

		newCmd := buildFn()
		if err := newCmd.Start(); err != nil {
			logWarnf("node restart failed: %v — retry in 2m", err)
			select {
			case <-shutdown:
				return
			case <-time.After(nodeRestartDelay):
			}
			continue
		}
		runner.setCmd(newCmd)
		logOKf("node restarted after crash pid=%d port=%d", newCmd.Process.Pid, port)
		waitHealthy(port)
	}
}
