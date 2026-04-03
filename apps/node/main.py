"""
Local node WSGI: dashboard, shares, media, torrent snapshot publish.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import threading
import time
import traceback
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse  # gallery / marketplace / tasks

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("NODEADLINE_RUNTIME_DIR", os.path.join(_ROOT, "data"))

from libs.auth import config, session, delegated, users, port_manager, oauth_google, dns_claim_node
from libs.media import pipeline
from libs.protocol import RuntimeState
from libs.protocol import ShareEntry
from libs.shares import folder_picker, registry, indexer
from libs.system import disks
from libs.system import memory_stats
from libs.system.node_cleanup import terminate_other_node_instances
from libs.tasks import queue as task_queue
from libs.site_sync import fetch_site_channel, get_active_site_root, site_status, start_background_sync, sync_once
from libs.site_sync.ffmpeg_sync import start_ffmpeg_background_sync
from libs.stats.dashboard import build_dashboard_stats
from libs.torrent import worker as torrent_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("node")

_DISK_BENCH_LOCK = threading.Lock()

_RUNTIME_DIR = os.environ.get("NODEADLINE_RUNTIME_DIR", os.path.join(_ROOT, "data"))


def _public_url_scheme() -> str:
    """Прямой доступ к ноде по порту — HTTP; HTTPS задайте при reverse-proxy (NODEADLINE_PUBLIC_URL_SCHEME=https)."""
    s = os.environ.get("NODEADLINE_PUBLIC_URL_SCHEME", "http").strip().lower()
    return "https" if s == "https" else "http"


def _port_status_dict(environ: dict[str, Any] | None = None) -> dict[str, Any]:
    st = port_manager.load_state(_RUNTIME_DIR)
    d = st.to_dict()
    # Подмешиваем почту из сессии только в ответ (без save_state), чтобы не дергать диск и
    # on_wan_updated на каждом опросе /api/port/status — это могло давать сбои после OAuth.
    if environ is not None:
        try:
            sess = _session(environ)
            if sess:
                em = str(sess.get("email") or "").strip()
                if em and not (d.get("oauth_email") or "").strip():
                    d["oauth_email"] = em
                sub = str(sess.get("sub") or "").strip()
                if sub and not (d.get("oauth_bound_sub") or "").strip():
                    d["oauth_bound_sub"] = sub
        except Exception:
            pass
    if st.dns_public_https_url:
        d["public_base_url"] = st.dns_public_https_url
    elif st.dns_fqdn and st.dns_status == "ok":
        if st.public_port:
            d["public_base_url"] = f"{_public_url_scheme()}://{st.dns_fqdn}:{int(st.public_port)}/"
        else:
            d["public_base_url"] = f"{_public_url_scheme()}://{st.dns_fqdn}/"
    else:
        d["public_base_url"] = None
    pd = st.port_last_diag
    if pd:
        try:
            d["port_diag"] = json.loads(pd)
        except json.JSONDecodeError:
            d["port_diag"] = {"raw": pd[:800]}
    else:
        d["port_diag"] = None
    return d


def _request_base_url(environ: dict[str, Any]) -> str | None:
    """Текущий origin запроса (Host + схема), чтобы показать адрес, с которого открыт дашборд."""
    try:
        scheme = (environ.get("wsgi.url_scheme") or "http").strip().lower()
        if scheme not in ("http", "https"):
            scheme = "http"
        host = (environ.get("HTTP_HOST") or "").strip()
        if not host:
            sn = (environ.get("SERVER_NAME") or "").strip()
            port = (environ.get("SERVER_PORT") or "").strip()
            if sn:
                if port and port not in ("80", "443"):
                    host = f"{sn}:{port}"
                else:
                    host = sn
        if not host:
            return None
        return f"{scheme}://{host}/"
    except Exception:
        return None


def _share_with_index_stats(s: ShareEntry) -> dict[str, Any]:
    d = s.to_dict()
    fc, tb = registry.share_index_ready_stats(s.share_id)
    d["indexed_files"] = fc
    d["indexed_bytes"] = tb
    ft, fb = registry.share_files_total_stats(s.share_id)
    d["files_total"] = ft
    d["files_total_bytes"] = fb
    d["media_pending"] = registry.count_pending_media(s.share_id)
    return d
# Шары (shares.db), tasks.db, превью, users.json — в NODEADLINE_RUNTIME_DIR (см. node_main / installer).
# Раньше использовался join(_ROOT, "data") внутри каталога app payload — при обновлении приложения папка
# app перезаписывалась и список папок «пропадал». Переопределение: NODEADLINE_DATA_DIR.
_DATA_DIR = os.environ.get("NODEADLINE_DATA_DIR", _RUNTIME_DIR)


def _migrate_legacy_app_data_if_needed() -> None:
    """Однократный перенос из старого app/data в runtime после смены логики путей."""
    legacy = os.path.join(_ROOT, "data")
    if not os.path.isdir(legacy):
        return
    if os.path.abspath(_DATA_DIR) == os.path.abspath(legacy):
        return
    os.makedirs(_DATA_DIR, exist_ok=True)
    import shutil

    for fn in os.listdir(legacy):
        if not (fn.endswith(".db") or fn.endswith(".json")):
            continue
        src = os.path.join(legacy, fn)
        dst = os.path.join(_DATA_DIR, fn)
        if os.path.isfile(src) and not os.path.isfile(dst):
            try:
                shutil.copy2(src, dst)
                log.info("migrated data file %s -> %s", fn, _DATA_DIR)
            except OSError as e:
                log.warning("migrate %s: %s", fn, e)
    for fn in os.listdir(legacy):
        if "-wal" in fn or "-shm" in fn:
            src = os.path.join(legacy, fn)
            dst = os.path.join(_DATA_DIR, fn)
            if os.path.isfile(src) and not os.path.isfile(dst):
                try:
                    shutil.copy2(src, dst)
                except OSError:
                    pass
    prev_src = os.path.join(legacy, "previews")
    prev_dst = os.path.join(_DATA_DIR, "previews")
    if os.path.isdir(prev_src) and not os.path.isdir(prev_dst):
        try:
            shutil.copytree(prev_src, prev_dst)
            log.info("migrated previews -> %s", prev_dst)
        except OSError as e:
            log.warning("migrate previews: %s", e)


def _resolve_node_version() -> str:
    """Order: dev env override → runtime (installer sync from server) → baked-in payload file."""
    env = os.environ.get("NODEADLINE_VERSION")
    if env:
        return env
    try:
        p = os.path.join(_RUNTIME_DIR, "published_version.txt")
        with open(p, encoding="utf-8") as f:
            s = f.read().strip()
            if s:
                return s
    except OSError:
        pass
    try:
        p = os.path.join(_ROOT, "release_version.txt")
        with open(p, encoding="utf-8") as f:
            s = f.read().strip()
            if s:
                return s
    except OSError:
        pass
    return "2.0.0-dev"


def get_node_version() -> str:
    """Текущая строка версии узла (перечитывается с диска — совпадает с server version.json после sync установщика)."""
    return _resolve_node_version()


def _json(start_response, data: Any, status: str = "200 OK") -> list[bytes]:
    body = json.dumps(data, ensure_ascii=False).encode()
    start_response(status, [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ])
    return [body]


def _redirect(start_response, url: str) -> list[bytes]:
    start_response("302 Found", [("Location", url), ("Content-Length", "0")])
    return [b""]


def _text(start_response, msg: str, status: str = "200 OK") -> list[bytes]:
    b = msg.encode()
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(b)))])
    return [b]


def _html(start_response, html: str, status: str = "200 OK", *, no_cache: bool = False) -> list[bytes]:
    b = html.encode()
    headers: list[tuple[str, str]] = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(b))),
    ]
    if no_cache:
        headers.append(("Cache-Control", "no-store, no-cache, must-revalidate"))
    start_response(status, headers)
    return [b]


def _bytes(start_response, data: bytes, mime: str) -> list[bytes]:
    start_response("200 OK", [("Content-Type", mime), ("Content-Length", str(len(data)))])
    return [data]


def _serve_site_static(start_response, site_root: str, rel: str) -> list[bytes]:
    rel = rel.strip("/")
    parts = [p for p in rel.split("/") if p]
    if ".." in parts:
        return _text(start_response, "Not found", "404 Not Found")
    if not rel:
        fp = os.path.join(site_root, "index.html")
    elif rel.endswith("/"):
        fp = os.path.join(site_root, *parts, "index.html")
    else:
        fp = os.path.join(site_root, *parts)
    fp = os.path.normpath(fp)
    sroot = os.path.abspath(site_root)
    if not fp.startswith(sroot + os.sep) and fp != sroot:
        return _text(start_response, "Not found", "404 Not Found")
    if os.path.isdir(fp):
        idx = os.path.join(fp, "index.html")
        if os.path.isfile(idx):
            fp = idx
        else:
            return _text(start_response, "Not found", "404 Not Found")
    if not os.path.isfile(fp):
        return _text(start_response, "Not found", "404 Not Found")
    with open(fp, "rb") as f:
        raw = f.read()
    mime, _ = mimetypes.guess_type(fp)
    start_response(
        "200 OK",
        [
            ("Content-Type", mime or "application/octet-stream"),
            ("Cache-Control", "no-store, no-cache, must-revalidate"),
            ("Content-Length", str(len(raw))),
        ],
    )
    return [raw]


def _cookie(headers: list, payload: dict, environ: dict | None = None) -> None:
    tok = session.sign_session(payload, config.session_secret())
    secure = ""
    if environ is not None and (environ.get("wsgi.url_scheme") or "").lower() == "https":
        secure = "; Secure"
    c = f"{session.SESSION_COOKIE}={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={session.SESSION_TTL}{secure}"
    headers.append(("Set-Cookie", c))


def _session(environ) -> dict[str, Any] | None:
    raw = environ.get("HTTP_COOKIE", "")
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith(f"{session.SESSION_COOKIE}="):
            return session.verify_session(part.split("=", 1)[1], config.session_secret())
    return None


def _read(environ) -> bytes:
    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        n = 0
    return environ["wsgi.input"].read(n) if n else b""


def _require_owner(environ, start_response):
    s = _session(environ)
    if not s:
        return None, _json(start_response, {"error": "not_authenticated"}, "401 Unauthorized")
    return s, None


def _loopback(environ) -> bool:
    if os.environ.get("NODEADLINE_TRUST_PROXY", "").strip() in ("1", "true", "yes"):
        xff = (environ.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
        real = (environ.get("HTTP_X_REAL_IP") or "").strip()
        for a in (xff, real):
            if a and (a in ("127.0.0.1", "::1") or a.startswith("127.")):
                return True
    a = environ.get("REMOTE_ADDR", "")
    return a in ("127.0.0.1", "::1") or a.startswith("127.")


def _normalize_path_info(raw: str) -> str:
    """Ensure leading slash, collapse //, strip trailing slash except root."""
    p = (raw or "/").strip()
    if not p.startswith("/"):
        p = "/" + p
    while "//" in p:
        p = p.replace("//", "/")
    p = p.rstrip("/") or "/"
    return p


def _apply_forwarded_headers(environ: dict) -> None:
    """За reverse-proxy (HTTPS на ingress → нода на WAN:порт): корректные wsgi.url_scheme и SERVER_PORT.

    Иначе waitress превращает относительный Location в http://fqdn:37651/... — браузер бьётся в ingress:порт ноды и получает RST.
    """
    proto = (environ.get("HTTP_X_FORWARDED_PROTO") or "").strip().lower()
    if proto not in ("http", "https"):
        return
    environ["wsgi.url_scheme"] = proto
    ph = (environ.get("HTTP_X_FORWARDED_PORT") or "").strip()
    if ph.isdigit():
        environ["SERVER_PORT"] = ph
    elif proto == "https":
        environ["SERVER_PORT"] = "443"
    elif proto == "http":
        environ["SERVER_PORT"] = "80"
    fh = (environ.get("HTTP_X_FORWARDED_HOST") or "").strip()
    if fh:
        environ["HTTP_HOST"] = fh
        environ["SERVER_NAME"] = fh.split(":")[0].strip()


def _path_from_environ(environ: dict) -> str:
    """PATH_INFO from WSGI; fallback to REQUEST_URI if needed (some proxies)."""
    raw = environ.get("PATH_INFO")
    if raw is None or raw == "":
        uri = environ.get("REQUEST_URI") or environ.get("RAW_URI") or "/"
        if isinstance(uri, bytes):
            uri = uri.decode("latin-1", "replace")
        path = urlparse(uri).path if uri.startswith("http") else uri.split("?", 1)[0]
        raw = path or "/"
    if isinstance(raw, bytes):
        raw = raw.decode("latin-1", "replace")
    return _normalize_path_info(unquote(raw))


def _node_http_log(msg: str) -> None:
    try:
        logdir = os.path.join(_RUNTIME_DIR, "logs")
        os.makedirs(logdir, exist_ok=True)
        p = os.path.join(logdir, "node_http.log")
        line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg + "\n"
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


_HTTP_LOG_PLAIN_PATHS = frozenset({
    "/api/node/http-log",
    "/api/logs/http",
    "/api/logs",
})


def _remote_addr_is_private(environ: dict) -> bool:
    a = (environ.get("REMOTE_ADDR") or "").strip()
    if not a:
        return False
    a = a.split("%", 1)[0]
    try:
        ip = ipaddress.ip_address(a)
        return bool(ip.is_private or ip.is_loopback)
    except ValueError:
        return False


def _allow_disk_api(environ: dict) -> bool:
    """Диски, RAM/swap в /api/system/disks, лог: loopback, TRUST_PROXY, сессия, LAN, или NODEADLINE_DISK_API_PUBLIC."""
    if os.environ.get("NODEADLINE_DISK_API_PUBLIC", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    if _loopback(environ):
        return True
    if _session(environ):
        return True
    return _remote_addr_is_private(environ)


def _http_log_tail_response(start_response) -> list[bytes]:
    p = os.path.join(_RUNTIME_DIR, "logs", "node_http.log")
    max_bytes = 262_144
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            sz = f.tell()
            if sz <= max_bytes:
                f.seek(0)
                raw = f.read()
            else:
                f.seek(max(0, sz - max_bytes))
                raw = f.read()
        text = raw.decode("utf-8", errors="replace")
    except OSError:
        text = "(файл лога ещё не создан — откройте панель «Хранилище» или сделайте любой запрос к API.)\n"
    b = text.encode("utf-8")
    start_response("200 OK", [
        ("Content-Type", "text/plain; charset=utf-8"),
        ("Content-Length", str(len(b))),
        ("Cache-Control", "no-store"),
    ])
    return [b]


def _http_log_view_html_response(start_response) -> list[bytes]:
    """HTML-страница: перебирает /api/node/http-log и алиасы, показывает первый ответ 200."""
    html = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Лог HTTP ноды</title>
<style>body{font-family:system-ui,sans-serif;margin:1rem;max-width:56rem;background:#f8f9fa;color:#111}
pre{background:#fff;padding:1rem;border-radius:10px;white-space:pre-wrap;font-size:.82rem;border:1px solid #e9ecef}</style>
</head>
<body>
<h1>HTTP-лог ноды</h1>
<p id="p">Проверка эндпоинтов…</p>
<pre id="o"></pre>
<script>
(function(){
var paths=["/api/node/http-log","/api/logs/http","/api/logs"];
function next(i){
  if(i>=paths.length){document.getElementById("p").textContent="Ни один эндпоинт не ответил — обновите ноду до последней сборки.";return;}
  fetch(paths[i],{credentials:"same-origin"}).then(function(r){
    if(r.ok)return r.text();
    throw new Error();
  }).then(function(t){
    document.getElementById("p").textContent="Источник: "+paths[i];
    document.getElementById("o").textContent=t;
  }).catch(function(){next(i+1);});
}
next(0);
})();
</script>
</body>
</html>"""
    b = html.encode("utf-8")
    start_response("200 OK", [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(b))),
        ("Cache-Control", "no-store"),
    ])
    return [b]


def _fetch_master_version_json() -> dict[str, Any] | None:
    base = config.master_base_url().rstrip("/")
    url = f"{base}/version.json"
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "nodeadline-node/2"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _fetch_master_directory_users() -> dict[str, Any]:
    base = config.master_base_url().rstrip("/")
    url = f"{base}/api/directory/v1/users"
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "nodeadline-node/2"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode()
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"error": f"http_{e.code}", "users": []}
    except Exception as e:
        return {"error": str(e)[:240], "users": []}


def application(environ, start_response):
    _apply_forwarded_headers(environ)
    path = _path_from_environ(environ)
    method = environ.get("REQUEST_METHOD", "GET").upper()
    qs = environ.get("QUERY_STRING", "")

    try:
        if path in ("/core/dashboard", "/core", "/dashboard"):
            return _redirect(start_response, "/")

        if path == "/health":
            st = port_manager.load_state(_RUNTIME_DIR)
            ib = ""
            try:
                with open(os.path.join(_RUNTIME_DIR, "installer_build.txt"), encoding="utf-8") as f:
                    ib = f.read().strip()
            except OSError:
                pass
            return _json(start_response, {
                "ok": True,
                "role": "node",
                "version": get_node_version(),
                "installer_build": ib,
                "listen_port": st.listen_port,
                "ts": int(time.time()),
            })

        if path in _HTTP_LOG_PLAIN_PATHS and method == "GET":
            if not _allow_disk_api(environ):
                return _json(start_response, {"error": "disk_api_forbidden"}, "403 Forbidden")
            return _http_log_tail_response(start_response)

        if path == "/api/node/log-view" and method == "GET":
            if not _allow_disk_api(environ):
                return _json(start_response, {"error": "disk_api_forbidden"}, "403 Forbidden")
            return _http_log_view_html_response(start_response)

        if path == "/api/version":
            ib = ""
            try:
                with open(os.path.join(_RUNTIME_DIR, "installer_build.txt"), encoding="utf-8") as f:
                    ib = f.read().strip()
            except OSError:
                pass
            st = site_status(_RUNTIME_DIR)
            return _json(start_response, {
                "node_version": get_node_version(),
                "installer_build": ib,
                "site_revision": int(st.get("revision", 0) or 0),
                "site_active": bool(st.get("active")),
                "http_log_paths": ["/api/node/http-log", "/api/logs/http", "/api/logs"],
                "http_log_view": "/api/node/log-view",
                "site_log_viewer": "/site/node-log.html",
            })

        if path == "/api/edge/version" and method == "GET":
            data = _fetch_master_version_json()
            if not data:
                return _json(start_response, {"ok": False})
            return _json(
                start_response,
                {
                    "ok": True,
                    "version": str(data.get("version", "")).strip(),
                    "installer_build": str(data.get("installer_build", "")).strip(),
                    "windows_url": str(data.get("url", "")).strip(),
                    "linux_url": str(data.get("linux_url", "")).strip(),
                    "darwin_url": str(data.get("darwin_url", "")).strip(),
                },
            )

        if path == "/api/directory/users" and method == "GET":
            return _json(start_response, _fetch_master_directory_users())

        if path == "/api/site/status" and method == "GET":
            return _json(start_response, site_status(_RUNTIME_DIR))

        if path == "/api/site/master-channel" and method == "GET":
            ch = fetch_site_channel(config.master_base_url())
            if not ch:
                return _json(start_response, {"ok": False})
            return _json(
                start_response,
                {
                    "ok": True,
                    "revision": int(ch.get("revision", 0) or 0),
                    "bundle_sha256": str(ch.get("bundle_sha256", "")).strip().lower(),
                    "built_at_utc": str(ch.get("built_at_utc", "")).strip(),
                },
            )

        if path == "/api/site/sync-now" and method == "POST":
            if not _loopback(environ):
                return _json(
                    start_response,
                    {"ok": False, "error": "loopback_only"},
                    status="403 Forbidden",
                )

            def _run_sync_now() -> None:
                try:
                    applied, reason = sync_once(config.master_base_url(), _RUNTIME_DIR)
                    log.info("sync-now finished applied=%s reason=%s", applied, reason)
                except Exception:
                    log.exception("sync-now")

            threading.Thread(target=_run_sync_now, daemon=True).start()
            return _json(start_response, {"ok": True, "started": True})

        if path == "/api/system/apply-upgrade" and method == "POST":
            if not _allow_disk_api(environ):
                return _json(start_response, {"error": "disk_api_forbidden"}, "403 Forbidden")
            try:
                applied, reason = sync_once(config.master_base_url(), _RUNTIME_DIR)
            except Exception:
                log.exception("apply-upgrade: sync_once")
                return _json(start_response, {"ok": False, "error": "sync_failed"}, "500 Internal Server Error")
            try:
                killed = terminate_other_node_instances(_ROOT)
            except Exception:
                log.exception("apply-upgrade: terminate_other_node_instances")
                killed = []

            def _restart_later() -> None:
                time.sleep(0.45)
                _restart_node_process()

            threading.Thread(target=_restart_later, daemon=True, name="apply-upgrade-restart").start()
            return _json(
                start_response,
                {
                    "ok": True,
                    "site_sync_applied": applied,
                    "site_sync_reason": reason,
                    "terminated_pids": killed,
                    "restarting": True,
                },
            )

        if path == "/api/stats/dashboard" and method == "GET":
            return _json(
                start_response,
                build_dashboard_stats(_RUNTIME_DIR, config.master_base_url()),
            )

        if path == "/site" or path.startswith("/site/"):
            if method != "GET":
                return _text(start_response, "Method Not Allowed", "405 Method Not Allowed")
            if path == "/site":
                return _redirect(start_response, "/site/")
            site_root = get_active_site_root(_RUNTIME_DIR)
            if not site_root:
                return _html(
                    start_response,
                    "<!DOCTYPE html><html lang=ru><meta charset=utf-8><title>site</title>"
                    "<body><p style=font-family:system-ui>Канал сайта ещё не загружен — "
                    "подождите синхронизацию с nodeadline.online (около 1–2 мин).</p></body></html>",
                    no_cache=True,
                )
            rel = path[len("/site/") :]
            return _serve_site_static(start_response, site_root, rel)

        if path == "/assets/lottie/success.json" and method == "GET":
            lp = os.path.join(_HERE, "static", "lottie", "success.json")
            if not os.path.isfile(lp):
                return _text(start_response, "Not Found", "404 Not Found")
            with open(lp, "rb") as f:
                raw = f.read()
            start_response(
                "200 OK",
                [
                    ("Content-Type", "application/json; charset=utf-8"),
                    ("Cache-Control", "public, max-age=86400"),
                    ("Content-Length", str(len(raw))),
                ],
            )
            return [raw]

        if path == "/oauth/start":
            st = port_manager.load_state(_RUNTIME_DIR)
            p = st.listen_port or int(os.environ.get("PORT", "28473"))
            ret = f"http://127.0.0.1:{p}/oauth/callback"
            url = f"{config.master_base_url()}/api/oauth/v1/login?return_to={ret}"
            return _redirect(start_response, url)

        if path == "/oauth/callback":
            params = parse_qs(qs)
            err = (params.get("oauth_error") or params.get("error") or [""])[0]
            if err:
                return _text(start_response, f"OAuth error: {err}", "400 Bad Request")
            code = (params.get("redeem_code") or [""])[0]
            if not code:
                return _text(start_response, "No redeem_code", "400 Bad Request")
            try:
                info = delegated.node_exchange_code(master_url=config.master_base_url(), code=code)
            except Exception as e:
                return _text(start_response, f"Redeem failed: {e}", "500 Internal Server Error")
            if "error" in info:
                return _text(start_response, str(info["error"]), "400 Bad Request")
            sub = info.get("sub", "")
            email = info.get("email", "")
            uname = str(info.get("username") or "").strip() or oauth_google.normalize_username(email)
            user = users.upsert_user(
                sub=sub,
                email=email,
                name=info.get("name", ""),
                picture=info.get("picture", ""),
                username=uname,
            )
            tok = str(info.get("dns_claim_token") or "").strip()
            if tok and user.username:
                dns_claim_node.save_claim_context(
                    _RUNTIME_DIR,
                    token=tok,
                    username=user.username,
                    sub=str(sub),
                    email=str(user.email or email or ""),
                )
                threading.Thread(
                    target=lambda: dns_claim_node.try_claim_once(config.master_base_url(), _RUNTIME_DIR),
                    daemon=True,
                ).start()
            headers: list[tuple[str, str]] = []
            _cookie(headers, {
                "sub": sub,
                "email": user.email,
                "username": user.username,
                "exp": int(time.time()) + session.SESSION_TTL,
            }, environ)
            headers += [("Location", "/site/index.html?local=1"), ("Content-Length", "0")]
            start_response("302 Found", headers)
            return [b""]

        if path == "/api/me":
            s = _session(environ)
            if not s:
                return _json(start_response, {"authenticated": False})
            out: dict[str, Any] = dict(s)
            out["authenticated"] = True
            sub = str(s.get("sub") or "").strip()
            if sub:
                u = users.get_user_by_sub(sub)
                if u:
                    ud = u.to_dict()
                    out["picture"] = str(ud.get("picture") or "")
                    out["name"] = str(ud.get("name") or "")
                    if ud.get("email"):
                        out["email"] = str(ud["email"])
                    if ud.get("username"):
                        out["username"] = str(ud["username"])
            return _json(start_response, out)

        if path == "/api/session/handoff" and method == "GET":
            if not _loopback(environ):
                return _json(start_response, {"error": "loopback_only"}, "403 Forbidden")
            s = _session(environ)
            if not s:
                return _json(start_response, {"error": "not_authenticated"}, "401 Unauthorized")
            tok = session.sign_handoff(
                {
                    "sub": str(s.get("sub") or ""),
                    "email": str(s.get("email") or ""),
                    "username": str(s.get("username") or ""),
                },
                config.session_secret(),
            )
            return _json(start_response, {"token": tok})

        if path == "/api/session/claim" and method == "GET":
            params = parse_qs(qs)
            raw_tok = (params.get("token") or [""])[0]
            if not raw_tok.strip():
                return _text(start_response, "Missing token", "400 Bad Request")
            data = session.verify_handoff(raw_tok, config.session_secret())
            if not data:
                return _text(start_response, "Invalid or expired token", "400 Bad Request")
            sub = str(data.get("sub") or "").strip()
            email = str(data.get("email") or "").strip()
            username = str(data.get("username") or "").strip()
            if not sub:
                return _text(start_response, "Invalid token payload", "400 Bad Request")
            headers: list[tuple[str, str]] = []
            _cookie(headers, {"sub": sub, "email": email, "username": username}, environ)
            headers += [("Location", "/site/index.html?local=1"), ("Content-Length", "0")]
            start_response("302 Found", headers)
            return [b""]

        if path == "/api/logout" and method == "POST":
            sec = ""
            if (environ.get("wsgi.url_scheme") or "").lower() == "https":
                sec = "; Secure"
            c = f"{session.SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{sec}"
            start_response("200 OK", [("Set-Cookie", c), ("Content-Type", "application/json"), ("Content-Length", "2")])
            return [b"{}"]

        if path == "/api/diagnostics":
            if not _loopback(environ):
                return _json(start_response, {"error": "loopback_only"}, "403 Forbidden")
            st = port_manager.load_state(_RUNTIME_DIR)
            return _json(start_response, {
                "version": get_node_version(),
                "runtime_state": st.to_dict(),
                "config_role": config.role(),
                "loopback": _loopback(environ),
                "ffmpeg": pipeline.ffmpeg_available(),
            })

        if path in ("/api/system/disks", "/api/diagnostics/disks") and method == "GET":
            if not _allow_disk_api(environ):
                _node_http_log(
                    f"disks GET 403 disk_api_forbidden remote={environ.get('REMOTE_ADDR')!r} "
                    f"PATH_INFO={environ.get('PATH_INFO')!r}"
                )
                return _json(start_response, {"error": "disk_api_forbidden"}, "403 Forbidden")
            vols = disks.list_volumes()
            _node_http_log(
                f"disks GET 200 n={len(vols)} remote={environ.get('REMOTE_ADDR')!r} "
                f"path={path!r} raw_pi={environ.get('PATH_INFO')!r}"
            )
            log.info("disk api ok path=%s volumes=%d remote=%s", path, len(vols), environ.get("REMOTE_ADDR"))
            payload: dict[str, Any] = {
                "unit": "decimal_tb",
                "volumes": vols,
            }
            snap = memory_stats.host_memory_snapshot()
            payload.update(snap)
            return _json(start_response, payload)

        if path in ("/api/system/disks/benchmark", "/api/diagnostics/disks/benchmark") and method == "POST":
            if not _allow_disk_api(environ):
                return _json(start_response, {"error": "disk_api_forbidden"}, "403 Forbidden")
            body = json.loads(_read(environ))
            mp = str(body.get("mount_path") or body.get("mountpoint") or "").strip()
            if not mp:
                return _json(start_response, {"error": "mount_path_required"}, "400 Bad Request")
            size_mb = int(body.get("size_mb") or 16)
            with _DISK_BENCH_LOCK:
                out = disks.benchmark_mount(mp, size_mb=size_mb)
            return _json(start_response, out)

        if path == "/api/port/status":
            return _json(start_response, _port_status_dict(environ))

        if path == "/api/port/upnp" and method == "POST":
            if _loopback(environ):
                pass
            else:
                own, err = _require_owner(environ, start_response)
                if err:
                    return err
            st = port_manager.load_state(_RUNTIME_DIR)
            r = port_manager.try_upnp_mapping(st.listen_port)
            st.upnp_status = r.get("status", "failed")
            st.upnp_last_error = r.get("error")
            if r.get("external_port"):
                st.public_port = int(r["external_port"])
            if r.get("wan_ip"):
                st.wan_ip = str(r["wan_ip"])
            port_manager.save_state(_RUNTIME_DIR, st)
            return _json(start_response, r)

        if path == "/api/port/upnp-remap" and method == "POST":
            if _loopback(environ):
                pass
            else:
                own, err = _require_owner(environ, start_response)
                if err:
                    return err
            try:
                data = json.loads(_read(environ) or b"{}")
            except json.JSONDecodeError:
                data = {}
            raw_c = data.get("candidates")
            st = port_manager.load_state(_RUNTIME_DIR)
            lp = int(st.listen_port or 0)
            if not lp:
                return _json(start_response, {"error": "no_listen_port"}, "400 Bad Request")
            candidates: list[int] = []
            if isinstance(raw_c, list) and raw_c:
                for x in raw_c[:24]:
                    try:
                        p = int(x)
                        if 1 <= p <= 65535:
                            candidates.append(p)
                    except (TypeError, ValueError):
                        pass
            if not candidates:
                excl: set[int] = set()
                if st.public_port:
                    excl.add(int(st.public_port))
                candidates = port_manager.default_external_port_candidates(lp, also_exclude=excl)
            res = port_manager.try_upnp_remap_external(
                lp,
                previous_external=st.public_port,
                candidates=candidates,
                master_url=config.master_base_url(),
            )
            st2 = port_manager.load_state(_RUNTIME_DIR)
            if res.get("external_port"):
                st2.public_port = int(res["external_port"])
                w = res.get("wan_ip")
                if w:
                    st2.wan_ip = str(w)
                st2.upnp_status = "mapped"
                ok_probe = bool(res.get("reachable") or res.get("accepted_without_probe"))
                st2.upnp_last_error = None if ok_probe else (res.get("error") or "probe_unreachable")
                if res.get("reachable"):
                    st2.public_probe_status = "reachable"
                elif res.get("accepted_without_probe"):
                    st2.public_probe_status = "unknown"
                else:
                    st2.public_probe_status = "unreachable"
                st2.last_verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            else:
                st2.public_port = None
                st2.public_probe_status = "unknown"
                st2.upnp_status = "failed"
                st2.upnp_last_error = str(res.get("error") or "remap_failed")
            try:
                st2.port_last_diag = json.dumps(
                    {
                        "attempts": res.get("attempts"),
                        "reachable": res.get("reachable"),
                        "error": res.get("error"),
                        "candidates_tried": len(candidates),
                    },
                    ensure_ascii=False,
                )[:4000]
            except Exception:
                st2.port_last_diag = None
            port_manager.save_state(_RUNTIME_DIR, st2)
            out = dict(res)
            out["state"] = _port_status_dict(environ)
            return _json(start_response, out)

        if path == "/api/port/probe" and method == "POST":
            if not _loopback(environ):
                own, err = _require_owner(environ, start_response)
                if err:
                    return err
            # На localhost — без входа; иначе только владелец.
            st = port_manager.load_state(_RUNTIME_DIR)
            if not st.wan_ip or not st.public_port:
                return _json(start_response, {"error": "need_wan_and_public_port"}, "400 Bad Request")
            pr = port_manager.probe_via_master(config.master_base_url(), st.wan_ip, int(st.public_port))
            st.public_probe_status = "reachable" if pr.get("reachable") else "unreachable"
            st.last_verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            port_manager.save_state(_RUNTIME_DIR, st)
            return _json(start_response, pr)

        if path == "/api/port/manual" and method == "POST":
            # С localhost — без входа; с другого хоста — только владелец.
            if not _loopback(environ):
                own, err = _require_owner(environ, start_response)
                if err:
                    return err
            body = json.loads(_read(environ))
            st = port_manager.load_state(_RUNTIME_DIR)
            pp = int(body.get("public_port", 0) or 0)
            st.public_port = pp if pp else None
            wan_in = body.get("wan_ip")
            if isinstance(wan_in, str) and wan_in.strip():
                st.wan_ip = wan_in.strip()
            st.upnp_status = "manual"
            port_manager.save_state(_RUNTIME_DIR, st)
            probe_out: dict[str, Any] | None = None
            if st.wan_ip and st.public_port:
                pr = port_manager.probe_via_master(
                    config.master_base_url(), str(st.wan_ip), int(st.public_port)
                )
                st = port_manager.load_state(_RUNTIME_DIR)
                st.public_probe_status = "reachable" if pr.get("reachable") else "unreachable"
                st.last_verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                port_manager.save_state(_RUNTIME_DIR, st)
                probe_out = pr
            return _json(
                start_response,
                {
                    "ok": True,
                    "state": _port_status_dict(environ),
                    "probe": probe_out,
                },
            )

        if path == "/api/shares" and method == "GET":
            sess = _session(environ)
            gsub = str(sess.get("sub")) if sess else None
            return _json(
                start_response,
                [_share_with_index_stats(s) for s in registry.list_shares_for_session(gsub)],
            )

        if path == "/api/shares/pick-folder" and method == "POST":
            if not _loopback(environ):
                return _json(start_response, {"error": "loopback_only"}, "403 Forbidden")
            pth, perr = folder_picker.pick_local_folder()
            if perr:
                return _json(start_response, {"ok": False, "error": perr})
            return _json(start_response, {"ok": True, "path": pth})

        if path == "/api/shares" and method == "POST":
            if _loopback(environ):
                sess = _session(environ)
                owner_sub = str(sess.get("sub", "")) if sess else ""
            else:
                own, err = _require_owner(environ, start_response)
                if err:
                    return err
                owner_sub = str(own.get("sub") or "")
            body = json.loads(_read(environ))
            vis = body.get("visibility", "public")
            if vis not in ("public", "private"):
                return _json(start_response, {"error": "bad_visibility"}, "400 Bad Request")
            ent = registry.add_share(
                local_path=body["local_path"],
                mount_path=body.get("mount_path", ""),
                owner_sub=owner_sub,
                visibility=vis,
            )
            task_queue.enqueue(
                kind="index_share",
                payload={"share_id": ent.share_id, "local_path": ent.local_path},
                share_id=ent.share_id,
            )
            return _json(start_response, ent.to_dict(), "201 Created")

        if path.startswith("/api/shares/") and method == "PATCH":
            parts = path.split("/")
            if len(parts) == 4 and parts[3]:
                sid = parts[3]
                if sid in ("public", "pick-folder"):
                    return _text(start_response, "Not found", "404 Not Found")
                sh = registry.get_share(sid)
                if not sh:
                    return _text(start_response, "Not found", "404 Not Found")
                sess = _session(environ)
                sub = str(sess.get("sub") or "") if sess else ""
                if sh.owner_sub:
                    if sub != sh.owner_sub:
                        return _text(start_response, "Forbidden", "403 Forbidden")
                else:
                    if not sess and not _loopback(environ):
                        return _text(start_response, "Forbidden", "403 Forbidden")
                body = json.loads(_read(environ))
                vis = body.get("visibility")
                if vis not in ("public", "private"):
                    return _json(start_response, {"error": "bad_visibility"}, "400 Bad Request")
                registry.update_share_visibility(sid, vis)
                sh2 = registry.get_share(sid)
                return _json(start_response, {"ok": True, "share": sh2.to_dict() if sh2 else {}})

        if path.endswith("/publish-snapshot") and method == "POST":
            own, err = _require_owner(environ, start_response)
            if err:
                return err
            sid = path.split("/")[3]
            sh = registry.get_share(sid)
            if not sh or sh.owner_sub != own.get("sub"):
                return _text(start_response, "Forbidden", "403 Forbidden")
            st = port_manager.load_state(_RUNTIME_DIR)
            out = torrent_worker.publish_and_register(
                share_id=sid,
                owner_sub=own["sub"],
                master_url=config.master_base_url(),
                announce_url=str(config.tracker_section().get("announce_url") or f"{config.master_base_url()}/bt/announce"),
                listen_port=st.listen_port,
            )
            return _json(start_response, out)

        if path.startswith("/api/shares/") and method == "DELETE":
            parts = path.split("/")
            if len(parts) == 4 and parts[3]:
                sid = parts[3]
                sh = registry.get_share(sid)
                if not sh:
                    return _text(start_response, "Not found", "404 Not Found")
                sess = _session(environ)
                if sess:
                    sub = str(sess.get("sub") or "")
                    if sh.owner_sub not in ("", sub):
                        return _text(start_response, "Forbidden", "403 Forbidden")
                else:
                    if sh.owner_sub != "" or not _loopback(environ):
                        return _text(start_response, "Forbidden", "403 Forbidden")
                registry.remove_share(sid)
                return _json(start_response, {"ok": True})

        if path.endswith("/tree") and method == "GET" and path.startswith("/api/shares/"):
            parts = path.split("/")
            sid = parts[3] if len(parts) > 3 else ""
            sh = registry.get_share(sid)
            if not sh:
                return _text(start_response, "Not found", "404 Not Found")
            sess = _session(environ)
            if sh.visibility != "public" and (not sess or sess.get("sub") != sh.owner_sub):
                return _text(start_response, "Forbidden", "403 Forbidden")
            files = registry.list_files(sid, "", 10000, 0)
            return _json(start_response, {"share_id": sid, "files": files})

        if "/file" in path and method == "GET" and path.startswith("/api/shares/") and not path.startswith("/api/shares/public"):
            sid = path.split("/")[3]
            sh = registry.get_share(sid)
            if not sh:
                return _text(start_response, "Not found", "404 Not Found")
            sess = _session(environ)
            if sh.visibility != "public" and (not sess or sess.get("sub") != sh.owner_sub):
                return _text(start_response, "Forbidden", "403 Forbidden")
            params = parse_qs(qs)
            rel = unquote((params.get("path") or [""])[0])
            ab = registry.safe_resolve_path(sh, rel)
            if not ab or not os.path.isfile(ab):
                return _text(start_response, "Not found", "404 Not Found")
            import mimetypes
            mime, _ = mimetypes.guess_type(ab)
            with open(ab, "rb") as f:
                data = f.read()
            return _bytes(start_response, data, mime or "application/octet-stream")

        if path == "/api/shares/public" and method == "GET":
            return _json(
                start_response,
                [_share_with_index_stats(s) for s in registry.list_shares(public_only=True)],
            )

        if path == "/api/marketplace" and method == "GET":
            if not _allow_disk_api(environ):
                return _json(start_response, {"error": "forbidden"}, "403 Forbidden")
            sess = _session(environ)
            gsub = str(sess.get("sub")) if sess else None
            share_ids = [s.share_id for s in registry.list_shares_for_session(gsub)]
            params = parse_qs(qs)
            try:
                page = max(1, int((params.get("page") or ["1"])[0] or 1))
            except ValueError:
                page = 1
            try:
                per_page = min(100, max(1, int((params.get("per_page") or ["100"])[0] or 100)))
            except ValueError:
                per_page = 100
            total = registry.count_marketplace_media(share_ids)
            offset = (page - 1) * per_page
            rows = registry.list_marketplace_media(share_ids, per_page, offset)
            from libs.media.poster_sidecar import poster_relpath_for_image

            items: list[dict[str, Any]] = []
            for r in rows:
                rel = str(r.get("relative_path") or "")
                sid = str(r.get("share_id") or "")
                mt = str(r.get("media_type") or "")
                poster_rel = poster_relpath_for_image(rel)
                view_q = quote(rel, safe="")
                poster_q = quote(poster_rel, safe="")
                # Превью в сетке: для изображений — оригинал (браузер рисует jpg/png/webp).
                # Постер *_poster.jpg без ffmpeg/Pillow может отсутствовать — тогда ссылка была бы битой.
                if mt == "image":
                    thumb_path_q = view_q
                    thumb_relpath_out = rel
                else:
                    thumb_path_q = poster_q
                    thumb_relpath_out = poster_rel
                items.append(
                    {
                        "share_id": sid,
                        "public_slug": str(r.get("public_slug") or ""),
                        "mount_path": str(r.get("mount_path") or ""),
                        "relative_path": rel,
                        "indexed_at": str(r.get("indexed_at") or ""),
                        "media_type": mt,
                        "thumb_relpath": thumb_relpath_out,
                        "view_url": f"/api/shares/{sid}/file?path={view_q}",
                        "thumb_url": f"/api/shares/{sid}/file?path={thumb_path_q}",
                    }
                )
            pst = _port_status_dict(environ)
            return _json(
                start_response,
                {
                    "ok": True,
                    "items": items,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "public_base_url": pst.get("public_base_url"),
                    "site_origin": _request_base_url(environ),
                },
            )

        if path.startswith("/p/") and method == "GET" and "/file" not in path:
            parts_pub = [p for p in path.strip("/").split("/") if p]
            if len(parts_pub) == 3 and parts_pub[0] == "p" and parts_pub[2] == "gallery":
                slug_g = parts_pub[1]
                sh_g = registry.get_share_by_slug(slug_g)
                if not sh_g or sh_g.visibility != "public":
                    return _text(start_response, "Not found", "404 Not Found")
                params_g = parse_qs(qs)
                try:
                    page = max(1, int((params_g.get("page") or ["1"])[0] or 1))
                except ValueError:
                    page = 1
                try:
                    per_page = min(100, max(1, int((params_g.get("per_page") or ["24"])[0] or 24)))
                except ValueError:
                    per_page = 24
                total_g = registry.count_gallery_images(sh_g.share_id)
                offset_g = (page - 1) * per_page
                gallery_files = registry.list_gallery_images(sh_g.share_id, per_page, offset_g)
                from apps.node.user_page import render_public_gallery_page

                html_g = render_public_gallery_page(
                    mount=sh_g.mount_path,
                    slug=slug_g,
                    files=gallery_files,
                    page=page,
                    per_page=per_page,
                    total=total_g,
                )
                return _html(start_response, html_g, no_cache=True)

        if path.startswith("/p/") and "/file" in path and method == "GET":
            parts = path.split("/")
            slug = parts[2]
            sh = registry.get_share_by_slug(slug)
            if not sh or sh.visibility != "public":
                return _text(start_response, "Not found", "404 Not Found")
            params = parse_qs(qs)
            rel = unquote((params.get("path") or [""])[0])
            ab = registry.safe_resolve_path(sh, rel)
            if not ab or not os.path.isfile(ab):
                return _text(start_response, "Not found", "404 Not Found")
            import mimetypes
            mime, _ = mimetypes.guess_type(ab)
            with open(ab, "rb") as f:
                data = f.read()
            return _bytes(start_response, data, mime or "application/octet-stream")

        if path.startswith("/p/") and method == "GET" and path.count("/") == 2:
            slug = path.split("/")[2]
            sh = registry.get_share_by_slug(slug)
            if not sh or sh.visibility != "public":
                return _text(start_response, "Not found", "404 Not Found")
            files = registry.list_files(sh.share_id, "", 5000, 0)
            from apps.node.user_page import render_public_share_page
            html = render_public_share_page(mount=sh.mount_path, slug=slug, files=files)
            return _html(start_response, html, no_cache=True)

        if path == "/api/tasks/status" and method == "GET":
            if not _allow_disk_api(environ):
                return _json(start_response, {"error": "disk_api_forbidden"}, "403 Forbidden")
            return _json(start_response, task_queue.get_status_snapshot())

        if path == "/api/tasks/history" and method == "GET":
            if not _allow_disk_api(environ):
                return _json(start_response, {"error": "disk_api_forbidden"}, "403 Forbidden")
            params = parse_qs(qs)
            try:
                lim = int((params.get("limit") or ["50"])[0] or 50)
            except ValueError:
                lim = 50
            try:
                off = int((params.get("offset") or ["0"])[0] or 0)
            except ValueError:
                off = 0
            sort_raw = (params.get("sort") or ["created_desc"])[0] or "created_desc"
            sort_mode = "priority" if str(sort_raw).strip().lower() == "priority" else "created_desc"
            tasks, total = task_queue.list_tasks_recent(limit=lim, offset=off, sort_mode=sort_mode)
            try:
                done_lim = int((params.get("done_limit") or ["12"])[0] or 12)
            except ValueError:
                done_lim = 12
            done_lim = max(0, min(done_lim, 24))
            recent_done = task_queue.list_recent_done(limit=done_lim) if done_lim else []
            return _json(
                start_response,
                {
                    "ok": True,
                    "tasks": tasks,
                    "recent_done": recent_done,
                    "total": total,
                    "sort": sort_mode,
                    "limit": lim,
                    "offset": off,
                },
            )

        if path == "/api/tasks/reindex-all" and method == "POST":
            if not _allow_disk_api(environ):
                return _json(start_response, {"error": "forbidden"}, "403 Forbidden")
            sess = _session(environ)
            gsub = str(sess.get("sub")) if sess else None
            shares = registry.list_shares_for_session(gsub)
            n = 0
            for s in shares:
                task_queue.enqueue(
                    kind="index_share",
                    payload={"share_id": s.share_id, "local_path": s.local_path},
                    share_id=s.share_id,
                )
                n += 1
            return _json(start_response, {"ok": True, "enqueued": n})

        if path == "/api/media/status":
            return _json(start_response, {"ffmpeg": pipeline.ffmpeg_available()})

        if path == "/api/media/jobs" and method == "GET":
            params = parse_qs(qs)
            st = (params.get("status") or [None])[0]
            return _json(start_response, pipeline.list_jobs(share_id=None, status=st))

        if path == "/api/torrent/status":
            return _json(start_response, torrent_worker.all_states())

        if path.startswith("/preview/"):
            fname = path.split("/preview/", 1)[-1]
            fpath = os.path.join(_DATA_DIR, "previews", fname)
            if not os.path.isfile(fpath):
                return _text(start_response, "Not found", "404 Not Found")
            import mimetypes
            mime, _ = mimetypes.guess_type(fpath)
            with open(fpath, "rb") as f:
                return _bytes(start_response, f.read(), mime or "application/octet-stream")

        if path == "/":
            # Дашборд — статика из канала /site/ (синк с мастера по BT + web seed), не HTML из Python.
            return _redirect(start_response, "/site/index.html?local=1")

        parts = path.strip("/").split("/")
        if len(parts) == 1 and parts[0] and not parts[0].startswith("api"):
            # Старые закладки /{username}/ → тот же статический дашборд.
            return _redirect(start_response, "/site/index.html?local=1")

        _node_http_log(
            f"404 {method} {path!r} PATH_INFO={environ.get('PATH_INFO')!r} "
            f"REQUEST_URI={environ.get('REQUEST_URI')!r} SCRIPT_NAME={environ.get('SCRIPT_NAME')!r} "
            f"remote={environ.get('REMOTE_ADDR')!r}"
        )
        log.warning(
            "404 %s %s PATH_INFO=%r REQUEST_URI=%r",
            method,
            path,
            environ.get("PATH_INFO"),
            environ.get("REQUEST_URI"),
        )
        return _text(start_response, "Not Found", "404 Not Found")

    except Exception:
        log.exception("%s %s", method, path)
        return _text(start_response, traceback.format_exc(), "500 Internal Server Error")


def _preview_done(file_id: int) -> None:
    registry.set_preview_ready(file_id, 1)
    sid = registry.get_share_id_for_file(file_id)
    if sid:
        from libs.shares import index_manifest

        index_manifest.touch(sid, _DATA_DIR)


def _restart_node_process() -> None:
    """Перезапуск процесса после смены payload/версии (ручная подмена или установщик без supervisor)."""
    entry = os.path.join(_ROOT, "node_main.py")
    if not os.path.isfile(entry):
        log.error("auto-restart: нет %s — пропуск", entry)
        return
    try:
        os.chdir(_ROOT)
    except OSError:
        pass
    os.environ["PYTHONUNBUFFERED"] = "1"
    log.info("auto-restart: exec %s -u %s", sys.executable, entry)
    try:
        os.execv(sys.executable, [sys.executable, "-u", entry])
    except OSError:
        log.exception("auto-restart: exec failed")
        os._exit(4)


def _start_payload_auto_restart_watcher() -> None:
    """Следит за last_payload_sha256.txt (новый payload на диске) и перезапускает процесс.

    Установщик при смене payload останавливает ноду сам; этот поток нужен при ручной подмене
    файлов или если процесс остался старым. published_version.txt не смотрим — его часто
    перезаписывают без смены кода.
    """
    if os.environ.get("NODEADLINE_DISABLE_AUTO_RESTART", "").strip().lower() in ("1", "true", "yes", "on"):
        log.info("auto-restart отключён (NODEADLINE_DISABLE_AUTO_RESTART)")
        return

    def read_text(p: str) -> str | None:
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    try:
        interval = int(os.environ.get("NODEADLINE_RESTART_WATCH_SEC", "30").strip() or "30")
    except ValueError:
        interval = 30
    interval = max(10, min(interval, 600))

    sha_path = os.path.join(_RUNTIME_DIR, "last_payload_sha256.txt")
    main_py = os.path.join(_ROOT, "apps", "node", "main.py")
    watch_code = os.environ.get("NODEADLINE_WATCH_CODE", "").strip().lower() in ("1", "true", "yes", "on")

    prev_sha = read_text(sha_path)
    prev_mtime: float | None = None
    if watch_code and os.path.isfile(main_py):
        try:
            prev_mtime = os.path.getmtime(main_py)
        except OSError:
            prev_mtime = None

    log.info(
        "auto-restart watch: каждые %ds — %s%s",
        interval,
        os.path.basename(sha_path),
        " + apps/node/main.py" if watch_code else "",
    )

    def loop() -> None:
        nonlocal prev_mtime, prev_sha
        while True:
            time.sleep(interval)
            cur_sha = read_text(sha_path)
            if cur_sha != prev_sha:
                log.info("auto-restart: изменился last_payload_sha256 (новый payload на диске)")
                _restart_node_process()
                return
            prev_sha = cur_sha
            if watch_code and os.path.isfile(main_py):
                try:
                    mt = os.path.getmtime(main_py)
                except OSError:
                    continue
                if prev_mtime is not None and mt != prev_mtime:
                    log.info("auto-restart: изменился apps/node/main.py (NODEADLINE_WATCH_CODE)")
                    _restart_node_process()
                    return
                prev_mtime = mt

    threading.Thread(target=loop, name="payload-restart-watch", daemon=True).start()


def main():
    _migrate_legacy_app_data_if_needed()
    os.makedirs(_DATA_DIR, exist_ok=True)
    log.info("node data dir (shares, tasks, previews): %s", _DATA_DIR)
    registry.set_data_dir(_DATA_DIR)
    pipeline.set_data_dir(_DATA_DIR)
    task_queue.set_data_dir(_DATA_DIR)
    users.set_data_dir(_DATA_DIR)
    pipeline.set_on_preview_done(_preview_done)

    cfg = config.node_section()
    expose = bool(cfg.get("expose_lan", False))
    host = "0.0.0.0" if expose else str(cfg.get("listen_host", "127.0.0.1"))
    candidates = [int(x) for x in (cfg.get("port_candidates") or [28473, 37651, 45123, 7332]) if int(x) > 0]
    preferred = int(cfg.get("listen_port", 0) or 0)
    envp = os.environ.get("PORT", "").strip()
    if envp:
        try:
            preferred = int(envp)
        except ValueError:
            pass
    port = port_manager.pick_port(host, preferred or None, candidates)
    state = RuntimeState(
        listen_host=host,
        listen_port=port,
        expose_lan=expose,
        pid=os.getpid(),
        network_mode="lan" if expose else "local",
    )
    port_manager.save_state(_RUNTIME_DIR, state)

    if cfg.get("auto_upnp", True):
        r = port_manager.try_upnp_mapping(port)
        state = port_manager.load_state(_RUNTIME_DIR)
        state.upnp_status = r.get("status", "failed")
        state.upnp_last_error = r.get("error")
        if r.get("external_port"):
            state.public_port = int(r["external_port"])
        if r.get("wan_ip"):
            state.wan_ip = str(r["wan_ip"])
        port_manager.save_state(_RUNTIME_DIR, state)

    def _probe_later():
        time.sleep(2)
        st = port_manager.load_state(_RUNTIME_DIR)
        if cfg.get("auto_probe_wan", True) and st.wan_ip and st.public_port:
            pr = port_manager.probe_via_master(config.master_base_url(), st.wan_ip, int(st.public_port))
            st.public_probe_status = "reachable" if pr.get("reachable") else "unreachable"
            st.last_verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            port_manager.save_state(_RUNTIME_DIR, st)

    threading.Thread(target=_probe_later, daemon=True).start()

    start_background_sync(config.master_base_url(), _RUNTIME_DIR)
    start_ffmpeg_background_sync(config.master_base_url(), _RUNTIME_DIR)
    dns_claim_node.start_dns_claim_loop(config.master_base_url(), _RUNTIME_DIR)
    dns_claim_node.sync_dns_pipeline_stage(_RUNTIME_DIR)

    def _open_local_site_landing():
        time.sleep(2.0)
        from libs.site_sync.browser_open import maybe_open_local_site

        for _ in range(60):
            maybe_open_local_site(_RUNTIME_DIR)
            time.sleep(0.5)

    threading.Thread(target=_open_local_site_landing, daemon=True).start()

    _start_payload_auto_restart_watcher()

    task_queue.start_worker(_DATA_DIR, _ROOT)
    log.info("task workers online (ffmpeg for video=%s)", pipeline.ffmpeg_available())

    import waitress

    logging.getLogger("waitress.queue").setLevel(logging.ERROR)

    wt = 8
    try:
        wt = max(4, int(os.environ.get("NODEADLINE_WAITRESS_THREADS", "8").strip() or "8"))
    except ValueError:
        wt = 8
    log.info("node %s:%d (waitress threads=%d)", host, port, wt)
    waitress.serve(application, host=host, port=port, threads=wt, _quiet=True)


if __name__ == "__main__":
    main()
