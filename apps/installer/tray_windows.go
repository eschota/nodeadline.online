//go:build windows

package main

import (
	"io"
	"log"
	"os"
	"os/exec"

	"fyne.io/systray"
	icon "fyne.io/systray/example/icon"
)

func runWindowsTray(_ io.Writer, _ chan struct{}, triggerShutdown func(), installerDone <-chan struct{}) {
	onReady := func() {
		systray.SetTemplateIcon(icon.Data, icon.Data)
		systray.SetTooltip("Nodeadline — локальная нода")
		systray.SetTitle("Nodeadline")

		systray.SetOnTapped(func() {
			openLocalURL(cabinetDashboardURL())
		})

		mOpen := systray.AddMenuItem("Открыть кабинет", "Локальный дашборд /site/")
		mLog := systray.AddMenuItem("Посмотреть лог", "installer.log в Notepad")
		mRestart := systray.AddMenuItem("Полная перезагрузка", "Перезапустить ноду и процесс")
		mQuit := systray.AddMenuItem("Выход", "Остановить ноду и выйти")

		go func() {
			for range mOpen.ClickedCh {
				openLocalURL(cabinetDashboardURL())
			}
		}()
		go func() {
			for range mLog.ClickedCh {
				openInstallerLog()
			}
		}()
		go func() {
			for range mRestart.ClickedCh {
				markTrayRestart()
				triggerShutdown()
				go func() {
					<-installerDone
					if takeTrayRestart() {
						relaunchInstaller()
					}
					systray.Quit()
				}()
			}
		}()
		go func() {
			for range mQuit.ClickedCh {
				triggerShutdown()
				go func() {
					<-installerDone
					systray.Quit()
				}()
			}
		}()
	}

	onExit := func() {}

	systray.Run(onReady, onExit)
}

func relaunchInstaller() {
	exe, err := os.Executable()
	if err != nil {
		log.Printf("relaunch: executable: %v", err)
		return
	}
	args := append([]string{}, os.Args[1:]...)
	hasSilent := false
	for _, a := range args {
		if a == "-silent" || a == "--silent" {
			hasSilent = true
			break
		}
	}
	if !hasSilent {
		args = append(args, "-silent")
	}
	cmd := exec.Command(exe, args...)
	cmd.Env = append(os.Environ(), "NODEADLINE_SKIP_PEER_KILL=1")
	cmd.Stdout = nil
	cmd.Stderr = nil
	cmd.Stdin = nil
	if err := cmd.Start(); err != nil {
		log.Printf("relaunch: start: %v", err)
		return
	}
	log.Printf("relaunch: started new installer pid=%d", cmd.Process.Pid)
}
