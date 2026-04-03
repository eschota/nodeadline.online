# FFmpeg (vendor + торрент-канал)

Статические **ffmpeg** и **ffprobe** для постеров изображений и видео (очередь `image_poster`, медиа-пайплайн).

## Локальная подстановка (разработка)

- `windows/ffmpeg.exe`, `windows/ffprobe.exe`
- `linux/ffmpeg`, `linux/ffprobe` (chmod +x)

Скачать готовые бинарники в дерево:

```bash
./tools/fetch_vendor_ffmpeg.sh
```

- Windows: [Gyan](https://www.gyan.dev/ffmpeg/builds/) — *essentials* (полный набор кодеков, один из меньших готовых zip).
- Linux amd64: [John Van Sickle](https://johnvansickle.com/ffmpeg/) — static build.

## Публикация и синхронизация у нод

После заполнения `vendor/ffmpeg/`:

```bash
python3 tools/build_ffmpeg_channel.py
```

Создаётся `public/ffmpeg_channel.json` и архивы с торрентами в `public/downloads/ffmpeg/`. При деплое `tools/deploy_public.sh` вызывает этот шаг автоматически, если бинарники есть.

Нода качает **только свой** вариант (Windows или Linux) в `NODEADLINE_RUNTIME_DIR/vendor/ffmpeg/…` по BitTorrent (как канал `/site/`) с fallback на HTTPS. Поиск бинарников: см. `libs/system/ffmpeg_paths.py` (сначала runtime, затем payload, затем `PATH`).

Лицензии сборок — GPL/LGPL у FFmpeg; распространение с вашим продуктом на условиях совместимых лицензий.
