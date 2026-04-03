Nodeadline — скриптовая установка без Go (.exe)
==============================================

Файлы:
  tools\windows\install-nodeadline.bat   — запуск из cmd / двойной щелчок
  tools\windows\install-nodeadline.ps1   — логика: venv → pip → node_main.py

Запуск из корня установки (где есть runtime\, как у инсталлятора):
  cd /d C:\Users\...\AppData\Local\nodeadline-v2
  tools\windows\install-nodeadline.bat

Или из клонированного репозитория (рядом с node_main.py и requirements-node.txt):
  tools\windows\install-nodeadline.bat

Поведение:
  - Создаётся runtime\venv при необходимости
  - pip ставит зависимости из requirements-node.txt
  - По умолчанию pip идёт в PyPI; таймаут 25 с, 2 попытки — при проблемах сеть падает быстро, без долгого ожидания
  - После установки запускается нода (waitress). Остановка: Ctrl+C

Параметры PowerShell (через bat те же):
  -InstallRoot "D:\path"     — явный корень
  -Offline                  — pip --no-index (нужен -Mirror или NODEADLINE_REQUIREMENTS_MIRROR)
  -Mirror "https://.../Nodeadline/Core/requirements/"
  -NoStart                  — только venv + pip, без запуска ноды
  -RecreateVenv             — пересоздать venv с нуля
  -PipTimeoutSec 20         — ещё короче таймаут pip
  -PipRetries 1

Пример только зависимости:
  powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\install-nodeadline.ps1 -NoStart

Это не замена официальному .exe-инсталлятору (автообновление payload, supervisor и т.д.), а быстрый обход при зависаниях pip --no-index в офлайн-режиме.
