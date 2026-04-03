"""JPG/PNG → {stem}_poster.jpg рядом с файлом; метаданные: родитель приоритетнее."""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)

PREVIEW_MAX_WIDTH = 600
POSTER_QUALITY = 85


def poster_relpath_for_image(rel: str) -> str:
    rel = rel.replace("\\", "/")
    d, base = os.path.split(rel)
    stem, _ext = os.path.splitext(base)
    name = f"{stem}_poster.jpg"
    return f"{d}/{name}" if d else name


def _dims(orig_w: int, orig_h: int) -> tuple[int, int]:
    if orig_w <= 0 or orig_h <= 0:
        return PREVIEW_MAX_WIDTH, PREVIEW_MAX_WIDTH
    if orig_w <= PREVIEW_MAX_WIDTH:
        return orig_w, orig_h
    ratio = PREVIEW_MAX_WIDTH / orig_w
    return PREVIEW_MAX_WIDTH, max(2, int(orig_h * ratio))


def _merge_exif_into_poster(src_path: str, poster_path: str, *, rel: str, size_bytes: int, modified_at: str) -> None:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        log.warning("Pillow not installed — poster without EXIF merge")
        return
    src_img = None
    dst_img = None
    try:
        src_img = Image.open(src_path)
        dst_img = Image.open(poster_path)
        ex = src_img.getexif()
        if ex is None:
            dst_img.save(poster_path, quality=POSTER_QUALITY)
            return
        try:
            uc = ex.get(37510)
            if isinstance(uc, bytes):
                parent_uc = uc.decode("utf-8", errors="replace")
            else:
                parent_uc = str(uc or "")
        except Exception:
            parent_uc = ""
        side = json.dumps(
            {"relative_path": rel.replace("\\", "/"), "size_bytes": size_bytes, "modified_at": modified_at},
            ensure_ascii=False,
        )
        if "nodeadline:" not in parent_uc:
            merged = (parent_uc + "\n" if parent_uc else "") + "nodeadline:" + side
            ex[37510] = merged.encode("utf-8")
        ex_bytes = ex.tobytes() if hasattr(ex, "tobytes") else None
        dst_img.save(poster_path, quality=POSTER_QUALITY, exif=ex_bytes)
    except UnidentifiedImageError:
        log.debug("exif merge: skip (unreadable poster or source): %s", poster_path)
    except OSError as e:
        log.debug("exif merge: skip (I/O): %s", e)
    except Exception as e:
        log.warning("exif merge: %s", e)
    finally:
        if dst_img is not None:
            try:
                dst_img.close()
            except Exception:
                pass
        if src_img is not None:
            try:
                src_img.close()
            except Exception:
                pass


def _ensure_rgb(img: "object") -> "object":
    from PIL import Image

    if not isinstance(img, Image.Image):
        raise TypeError("PIL Image expected")
    if getattr(img, "is_animated", False):
        img.seek(0)
    if img.mode == "CMYK":
        img = img.convert("RGB")
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            bg.paste(img, mask=img.split()[3])
        else:
            bg.paste(img)
        return bg
    if img.mode == "P" and "transparency" in img.info:
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        return bg
    return img.convert("RGB")


def _build_image_poster_pillow(
    *,
    src_abs: str,
    out_abs: str,
    rel: str,
    size_bytes: int,
    modified_at: str,
) -> str:
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(
            "Pillow не установлен: pip install Pillow (нужен для постеров изображений без ffmpeg)"
        ) from e
    img = Image.open(src_abs)
    img = _ensure_rgb(img)
    ow, oh = img.size
    pw, ph = _dims(ow, oh)
    if (ow, oh) != (pw, ph):
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = getattr(Image, "LANCZOS", 1)
        img = img.resize((pw, ph), resample)
    parent = os.path.dirname(out_abs)
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.save(out_abs, "JPEG", quality=POSTER_QUALITY, optimize=True)
    img.close()
    _merge_exif_into_poster(src_abs, out_abs, rel=rel, size_bytes=size_bytes, modified_at=modified_at)
    return out_abs


def build_image_poster(
    *,
    share_local_root: str,
    relative_path: str,
    size_bytes: int,
    modified_at: str,
) -> str:
    """Создаёт {stem}_poster.jpg через Pillow (без ffmpeg). Видео по-прежнему через ffmpeg в pipeline."""
    rel = relative_path.replace("\\", "/")
    src_abs = os.path.join(share_local_root, rel.replace("/", os.sep))
    prel = poster_relpath_for_image(rel)
    out_abs = os.path.join(share_local_root, prel.replace("/", os.sep))
    return _build_image_poster_pillow(
        src_abs=src_abs,
        out_abs=out_abs,
        rel=rel,
        size_bytes=size_bytes,
        modified_at=modified_at,
    )


def poster_up_to_date(share_local_root: str, relative_path: str) -> bool:
    rel = relative_path.replace("\\", "/")
    src = os.path.join(share_local_root, rel.replace("/", os.sep))
    prel = poster_relpath_for_image(rel)
    poster = os.path.join(share_local_root, prel.replace("/", os.sep))
    if not os.path.isfile(poster):
        return False
    try:
        return os.path.getmtime(poster) >= os.path.getmtime(src)
    except OSError:
        return False
