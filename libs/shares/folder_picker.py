"""
Native folder picker via OS dialogs (spawned by node process on the user's machine).

Browsers cannot expose a real filesystem path like C:\\Users\\... without a bridge;
this module runs when the user clicks "Choose folder" and the local WSGI spawns
the platform dialog in the same desktop session as the node process.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Tuple

# Long timeout: user may navigate slowly in the dialog
_PICK_TIMEOUT = 600.0


def pick_local_folder() -> Tuple[str | None, str | None]:
    """
    Block until the user picks a folder or cancels.
    Returns (absolute_path, None) or (None, error_or_cancel_message).
    """
    if sys.platform == "win32":
        return _pick_windows()
    if sys.platform == "darwin":
        return _pick_macos()
    return _pick_linux()


def _pick_windows() -> Tuple[str | None, str | None]:
    # Путь пишем в файл: так надёжнее, чем stdout (PS 7 / кодировки иногда подменяют вывод).
    fd, out_file = tempfile.mkstemp(suffix=".txt", prefix="ndl-pick-")
    os.close(fd)
    ps1 = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$fb = New-Object System.Windows.Forms.FolderBrowserDialog
$fb.Description = 'nodeadline — select folder to share'
$fb.ShowNewFolderButton = $true
$r = $fb.ShowDialog()
if ($r -eq [System.Windows.Forms.DialogResult]::OK) {
    $p = $fb.SelectedPath
    $out = $env:NODEADLINE_PICK_OUT
    if ($null -ne $p -and $p -ne '') {
        [System.IO.File]::WriteAllText($out, $p, [System.Text.UTF8Encoding]::new($false))
    }
}
"""
    fd, path = tempfile.mkstemp(suffix=".ps1", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(ps1)
        exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        if not os.path.isfile(exe):
            exe = "powershell.exe"
        # Нельзя -NonInteractive: WinForms FolderBrowserDialog считается интерактивным и не откроется.
        # CREATE_NO_WINDOW тоже не используем — иначе часто нет нормального message loop / показа диалога.
        env = os.environ.copy()
        env["NODEADLINE_PICK_OUT"] = out_file
        kwargs: dict = {
            "args": [
                exe,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Sta",
                "-File",
                path,
            ],
            "capture_output": True,
            "text": True,
            "encoding": "utf-8-sig",
            "errors": "replace",
            "timeout": _PICK_TIMEOUT,
            "env": env,
        }
        proc = subprocess.run(**kwargs)
        err_out = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
        if proc.returncode != 0:
            try:
                os.unlink(out_file)
            except OSError:
                pass
            return None, err_out or "folder dialog failed"
        try:
            with open(out_file, encoding="utf-8", errors="replace") as fp:
                raw = fp.read()
        except OSError:
            raw = ""
        try:
            os.unlink(out_file)
        except OSError:
            pass
        out = raw.strip()
        if not out:
            return None, "cancelled"
        if not os.path.isdir(out):
            return None, "selected path is not a directory"
        return os.path.normpath(os.path.abspath(out)), None
    except subprocess.TimeoutExpired:
        try:
            os.unlink(out_file)
        except OSError:
            pass
        return None, "timed out"
    except FileNotFoundError:
        try:
            os.unlink(out_file)
        except OSError:
            pass
        return None, "powershell.exe not found"
    except OSError as e:
        try:
            os.unlink(out_file)
        except OSError:
            pass
        return None, str(e)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _pick_macos() -> Tuple[str | None, str | None]:
    # Сначала alias в переменную, затем POSIX path — иначе бывает «… is not a dictionary».
    script = """
try
  set theFolder to choose folder with prompt "nodeadline — select folder to share"
  return POSIX path of theFolder
on error number -128
  return ""
end try
"""
    try:
        proc = subprocess.run(
            ["osascript", "-"],
            input=script,
            capture_output=True,
            text=True,
            timeout=_PICK_TIMEOUT,
        )
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return None, err or "osascript failed"
        out = (proc.stdout or "").strip()
        if not out:
            return None, "cancelled"
        p = out.rstrip("/")
        if not os.path.isdir(p):
            return None, "selected path is not a directory"
        return os.path.normpath(os.path.abspath(p)), None
    except FileNotFoundError:
        return None, "osascript not found"
    except subprocess.TimeoutExpired:
        return None, "timed out"


def _pick_linux() -> Tuple[str | None, str | None]:
    zen = shutil.which("zenity")
    if zen:
        try:
            proc = subprocess.run(
                [zen, "--file-selection", "--directory", "--title=Select folder to share", "--modal"],
                capture_output=True,
                text=True,
                timeout=_PICK_TIMEOUT,
            )
            out = (proc.stdout or "").strip()
            if proc.returncode != 0 or not out:
                return None, "cancelled"
            if not os.path.isdir(out):
                return None, "selected path is not a directory"
            return os.path.normpath(os.path.abspath(out)), None
        except subprocess.TimeoutExpired:
            return None, "timed out"
    kdialog = shutil.which("kdialog")
    if kdialog:
        try:
            proc = subprocess.run(
                [kdialog, "--getexistingdirectory", "."],
                capture_output=True,
                text=True,
                timeout=_PICK_TIMEOUT,
            )
            out = (proc.stdout or "").strip()
            if proc.returncode != 0 or not out:
                return None, "cancelled"
            if not os.path.isdir(out):
                return None, "selected path is not a directory"
            return os.path.normpath(os.path.abspath(out)), None
        except subprocess.TimeoutExpired:
            return None, "timed out"
    return None, "install zenity or kdialog for native folder picker on Linux"
