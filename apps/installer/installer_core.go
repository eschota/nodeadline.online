package main

import (
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// runInstallerCore runs payload sync, node, supervisor, updateLoop until shutdown is closed.
func runInstallerCore(shutdown <-chan struct{}, mw io.Writer) error {
	home, _ := os.UserHomeDir()
	installDir := envOr("NODEADLINE_INSTALL_DIR", defaultInstallDir(home))
	runtimeDir := filepath.Join(installDir, "runtime")
	setTrayRuntimeDir(runtimeDir)

	if err := os.MkdirAll(runtimeDir, 0755); err != nil {
		fatalExitf("FATAL: cannot create %s: %v", runtimeDir, err)
	}

	if envOr("NODEADLINE_SELF_UPGRADE", "") != "" {
		log.Printf("self-upgrade relaunch")
	}

	killOtherInstallerInstances()
	killExistingNodeListeners(runtimeDir)

	base := strings.TrimRight(envOr("NODEADLINE_BASE_URL", defaultBase), "/")
	appDir := filepath.Join(runtimeDir, "app")
	_ = os.MkdirAll(filepath.Join(installDir, "staging"), 0755)

	httpClient := newInstallerHTTPClient()
	runner := &nodeRunner{}
	tryInstallerUpgrade(httpClient, base, installDir, runtimeDir, runner, 0, false)

	venvPy := ensureVenv(installDir, runtimeDir)

	port := pickListenPort(runtimeDir)
	writePortFile(runtimeDir, port)

	tryInstallerUpgrade(httpClient, base, installDir, runtimeDir, runner, port, false)

	ib, _, syncErr := syncPayload(httpClient, base, installDir, appDir, venvPy, runner)
	if syncErr != nil {
		logWarnf("payload sync: %v", syncErr)
	}
	if ib != "" {
		writeLocalBuild(runtimeDir, ib)
	}

	nodeMain := filepath.Join(appDir, "node_main.py")
	if _, err := os.Stat(nodeMain); err != nil {
		log.Printf("FATAL: missing %s — need network first run or fix manifest/payload on server.", nodeMain)
		waitForUserOnWindows()
		os.Exit(1)
	}

	supervisorShutdown := make(chan struct{})
	buildNode := func() *exec.Cmd {
		return buildNodeCmd(venvPy, nodeMain, appDir, runtimeDir, port, base, mw)
	}
	go superviseNode(runner, buildNode, port, supervisorShutdown)

	cmd := buildNodeCmd(venvPy, nodeMain, appDir, runtimeDir, port, base, mw)
	if err := cmd.Start(); err != nil {
		fatalExitf("start node: %v", err)
	}
	runner.setCmd(cmd)
	logOKf("node pid=%d port=%d", cmd.Process.Pid, port)

	waitHealthy(port)

	go updateLoop(base, installDir, appDir, venvPy, runner, port, nodeMain, mw, runtimeDir, httpClient)

	<-shutdown
	runner.StopNode()
	close(supervisorShutdown)
	logInfof("shutdown")
	return nil
}
