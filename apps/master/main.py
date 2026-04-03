"""
nodeadline master WSGI: landing, OAuth, tracker, TCP probe, DNS claim (Namecheap).
"""
from __future__ import annotations

import html
import json
import logging
import os
import secrets
import socket
import sys
import time
import traceback
from typing import Any
from urllib.parse import parse_qs, urlencode

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from libs.auth import config, dns_registry, nginx_ingress, session, oauth_google, delegated, users
from libs.auth.directory import build_directory_entries
from libs.auth.hosted_subdomain import ensure_hosted_subdomain_after_oauth, is_hosted_binding
from libs.dns.namecheap_api import client_from_config, NamecheapError
from libs.protocol import DeployInfo
from libs.torrent import tracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("master")

_OAUTH_STATES: dict[str, dict[str, Any]] = {}
_OAUTH_TTL = 600
_PROBE_HITS: dict[str, list[float]] = {}


def _site_channel_revision_public() -> int:
    """Ревизия канала /site/ с диска мастера (тот же public/site_channel.json, что отдаётся нодам)."""
    p = os.path.join(_ROOT, "public", "site_channel.json")
    try:
        with open(p, encoding="utf-8") as f:
            return int(json.load(f).get("revision", 0) or 0)
    except Exception:
        return 0


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


def _html(start_response, html: str, status: str = "200 OK", *, head_only: bool = False) -> list[bytes]:
    b = html.encode()
    start_response(
        status,
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(b))),
            ("Cache-Control", "no-store, no-cache, must-revalidate"),
            ("Pragma", "no-cache"),
        ],
    )
    return [b""] if head_only else [b]


def _set_cookie(headers: list, payload: dict) -> None:
    tok = session.sign_session(payload, config.session_secret())
    c = f"{session.SESSION_COOKIE}={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={session.SESSION_TTL}"
    headers.append(("Set-Cookie", c))


def _get_session(environ) -> dict[str, Any] | None:
    raw = environ.get("HTTP_COOKIE", "")
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith(f"{session.SESSION_COOKIE}="):
            return session.verify_session(part.split("=", 1)[1], config.session_secret())
    return None


def _read_body(environ) -> bytes:
    try:
        n = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        n = 0
    return environ["wsgi.input"].read(n) if n else b""


def _subdomain_label(raw_host: str, apex: str) -> str | None:
    h = raw_host.strip().lower()
    a = apex.strip().lower()
    if not h.endswith("." + a) or h in (a, "www." + a):
        return None
    label = h[: -(len(a) + 1)]
    return label or None


def _wants_json_profile(environ: dict, qs: str) -> bool:
    p = parse_qs(qs)
    if (p.get("format") or [""])[0].lower() == "json":
        return True
    acc = (environ.get("HTTP_ACCEPT") or "").lower()
    if "text/html" in acc:
        return False
    return "application/json" in acc


def _user_cabinet_html(u: Any, binding: dict[str, Any] | None) -> str:
    name = html.escape(str(u.name or u.username or ""))
    uname = html.escape(str(u.username or ""))
    email = html.escape(str(u.email or ""))
    pic = html.escape(str(u.picture or ""), quote=True)
    fqdn = str((binding or {}).get("fqdn") or "").strip()
    site = f"https://{fqdn}/site/" if fqdn else ""
    base = html.escape(config.callback_base().rstrip("/"), quote=True)
    site_esc = html.escape(site, quote=True) if site else ""
    card = ""
    if pic:
        card += f'<img class="pic" src="{pic}" alt="" width="96" height="96" loading="lazy"/>'
    card += f"<h1>{name}</h1><p class=\"meta\">@{uname}</p><p class=\"email\">{email}</p>"
    if site:
        card += f'<p class="row"><a class="btn" href="{site_esc}">Открыть дашборд ноды (/site/)</a></p>'
    else:
        card += '<p class="meta">Поддомен появится после входа на мастере (OAuth).</p>'
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>nodeadline — {name}</title>
  <style>
    body{{font-family:system-ui,sans-serif;background:#0e0e12;color:#e8e8ec;margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;}}
    .card{{max-width:420px;background:#16161c;border:1px solid #2a2a34;border-radius:16px;padding:28px;box-sizing:border-box;}}
    .pic{{border-radius:50%;display:block;margin:0 auto 16px;}}
    h1{{font-size:1.35rem;margin:0 0 8px;text-align:center;}}
    .meta{{color:#8b8b9a;font-size:0.9rem;text-align:center;margin:0;}}
    .email{{text-align:center;margin:12px 0 0;font-size:0.95rem;}}
    .row{{margin-top:20px;text-align:center;}}
    .btn{{display:inline-block;background:#3b82f6;color:#fff;text-decoration:none;padding:10px 18px;border-radius:10px;font-weight:600;}}
    .foot{{margin-top:24px;font-size:0.8rem;color:#6a6a78;text-align:center;}}
    .foot a{{color:#93c5fd;}}
  </style>
</head>
<body>
  <div class="card">{card}
    <p class="foot">Корень сайта: <a href="{base}/">nodeadline.online</a> · JSON: <a href="{base}/{uname}/?format=json">?format=json</a></p>
  </div>
</body>
</html>"""


def _static(environ, start_response, rel: str) -> list[bytes] | None:
    rel = rel.lstrip("/")
    path = os.path.join(_ROOT, "public", rel)
    if not os.path.isfile(path):
        return None
    import mimetypes
    mime, _ = mimetypes.guess_type(path)
    with open(path, "rb") as f:
        data = f.read()
    headers: list[tuple[str, str]] = [
        ("Content-Type", mime or "application/octet-stream"),
        ("Content-Length", str(len(data))),
    ]
    if rel.endswith(".json"):
        headers.append(("Cache-Control", "no-store, no-cache, must-revalidate"))
    start_response("200 OK", headers)
    return [data]


def _rate_probe(ip: str) -> bool:
    now = time.time()
    lst = _PROBE_HITS.setdefault(ip, [])
    lst[:] = [t for t in lst if now - t < 60]
    if len(lst) >= 20:
        return False
    lst.append(now)
    return True


def _tcp_probe(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/").rstrip("/") or "/"
    method = environ.get("REQUEST_METHOD", "GET").upper()
    qs = environ.get("QUERY_STRING", "")
    remote = environ.get("REMOTE_ADDR", "0.0.0.0")

    try:
        if path == "/health":
            return _json(start_response, {"ok": True, "role": "master", "ts": int(time.time())})

        raw_host = (environ.get("HTTP_HOST") or "").split(":")[0].strip().lower()
        apex = str(config.namecheap_section().get("apex_domain") or "nodeadline.online").strip().lower()
        sub_lbl = _subdomain_label(raw_host, apex)
        if sub_lbl and method in ("GET", "HEAD"):
            seg = [p for p in path.strip("/").split("/") if p]
            want_site = path == "/" or (len(seg) == 1 and seg[0].lower() == sub_lbl)
            if want_site:
                for bb in dns_registry.load_all_bindings().values():
                    if str(bb.get("fqdn") or "").strip().lower() != raw_host:
                        continue
                    if is_hosted_binding(bb):
                        return _redirect(start_response, "/site/")
                    break

        if path.startswith("/downloads/") or path.startswith("/assets/"):
            r = _static(environ, start_response, path)
            if r:
                return r
            return _text(start_response, "Not Found", "404 Not Found")

        if path == "/version.json":
            r = _static(environ, start_response, "version.json")
            if r:
                return r
            return _json(start_response, {"version": "0.0.0", "manifest_url": ""})

        if path == "/build.json":
            r = _static(environ, start_response, "build.json")
            if r:
                return r
            return _text(start_response, "Not Found", "404 Not Found")

        if path == "/ffmpeg_channel.json":
            r = _static(environ, start_response, "ffmpeg_channel.json")
            if r:
                return r
            return _text(start_response, "Not Found", "404 Not Found")

        if path == "/deploy-info.json":
            di = DeployInfo(
                version=os.environ.get("NODEADLINE_VERSION", "dev"),
                deployed_at=os.environ.get("NODEADLINE_DEPLOYED_AT", ""),
                role="master",
            )
            return _json(start_response, json.loads(di.to_json()))

        if path == "/api/version" and method == "GET":
            # Та же статика /site/, что у ноды; дашборд опрашивает /api/version — помечаем ответ мастера.
            return _json(
                start_response,
                {
                    "role": "master",
                    "hosted_static_site": True,
                    "node_version": None,
                    "installer_build": "",
                    "master_version": os.environ.get("NODEADLINE_VERSION", "dev"),
                    "site_revision": _site_channel_revision_public(),
                },
            )

        # Не редиректить /site → /site/: PATH_INFO /site/ после rstrip("/") уже /site, редирект давал ERR_TOO_MANY_REDIRECTS.
        if path == "/site":
            r = _static(environ, start_response, "site/index.html")
            if r:
                return r
            return _text(start_response, "Not Found", "404 Not Found")
        if path.startswith("/site/"):
            rest = path[len("/site/") :]
            if not rest or rest == "/":
                site_rel = "site/index.html"
            else:
                site_rel = "site/" + rest.lstrip("/")
            r = _static(environ, start_response, site_rel)
            if r:
                return r
            return _text(start_response, "Not Found", "404 Not Found")

        if path in ("/core", "/"):
            from apps.master.download_page import core_landing_html

            landing = core_landing_html(base_url=config.callback_base())
            return _html(start_response, landing)

        if path == "/api/public/tcp-probe" and method == "GET":
            if not _rate_probe(remote):
                return _json(start_response, {"ok": False, "error": "rate_limited"}, "429 Too Many Requests")
            params = parse_qs(qs)
            host = (params.get("host") or [""])[0].strip()
            try:
                port = int((params.get("port") or ["0"])[0])
            except ValueError:
                port = 0
            if not host or not (1 <= port <= 65535):
                return _json(start_response, {"ok": False, "error": "bad_params"}, "400 Bad Request")
            cfg = config.tcp_probe_section()
            if not cfg.get("enabled", True):
                return _json(start_response, {"ok": False, "reachable": False, "error": "disabled"})
            ok = _tcp_probe(host, port)
            return _json(start_response, {"ok": True, "reachable": ok, "host": host, "port": port})

        if path == "/api/directory/v1/users" and method == "GET":
            if os.environ.get("NODEADLINE_DIRECTORY_DISABLE", "").strip().lower() in ("1", "true", "yes", "on"):
                return _json(start_response, {"error": "directory_disabled", "users": []}, "403 Forbidden")
            return _json(start_response, {"users": build_directory_entries()})

        if path == "/api/oauth/v1/login" and method == "GET":
            return _oauth_start(environ, start_response, qs)

        if path == "/oauth/google/callback" and method == "GET":
            return _oauth_cb(environ, start_response, qs)

        if path == "/api/oauth/v1/redeem" and method == "POST":
            body = _read_body(environ)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return _text(start_response, "Bad JSON", "400 Bad Request")
            code = data.get("code", "")
            ent = delegated.consume_redeem_code(code)
            if not ent:
                return _json(start_response, {"error": "invalid_or_expired_code"}, "400 Bad Request")
            out = dict(ent)
            sub = str(ent.get("sub") or "")
            if sub:
                u = users.get_user_by_sub(sub)
                if u:
                    out["username"] = str(u.username)
                out["dns_claim_token"] = session.sign_session(
                    {"sub": sub, "scope": "dns_claim"},
                    config.session_secret(),
                )
            return _json(start_response, out)

        if path == "/api/oauth/v1/me" and method == "GET":
            sess = _get_session(environ)
            if not sess:
                return _json(start_response, {"error": "not_authenticated"}, "401 Unauthorized")
            return _json(start_response, sess)

        if path == "/api/oauth/v1/logout" and method == "POST":
            c = f"{session.SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
            start_response("200 OK", [("Set-Cookie", c), ("Content-Type", "application/json"), ("Content-Length", "2")])
            return [b"{}"]

        if path == "/api/dns/v1/claim-subdomain" and method == "POST":
            sub_claim = ""
            sess = _get_session(environ)
            if sess:
                sub_claim = str(sess.get("sub") or "").strip()
            if not sub_claim:
                auth = environ.get("HTTP_AUTHORIZATION", "")
                if auth.startswith("Bearer "):
                    tok = auth.split(" ", 1)[1].strip()
                    pl = session.verify_session(tok, config.session_secret())
                    if pl and pl.get("scope") == "dns_claim":
                        sub_claim = str(pl.get("sub") or "").strip()
            if not sub_claim:
                return _json(start_response, {"error": "not_authenticated"}, "401 Unauthorized")
            try:
                data = json.loads(_read_body(environ))
            except json.JSONDecodeError:
                return _text(start_response, "Bad JSON", "400 Bad Request")
            label = str(data.get("label", "")).strip().lower().replace("_", "-")
            wan = str(data.get("wan_ipv4", "")).strip()
            try:
                public_port = int(data.get("public_port"))
            except (TypeError, ValueError):
                return _json(start_response, {"error": "public_port_required"}, "400 Bad Request")
            if not label or not wan:
                return _json(start_response, {"error": "label_and_wan_ipv4_required"}, "400 Bad Request")
            if public_port < 1 or public_port > 65535:
                return _json(start_response, {"error": "public_port_invalid"}, "400 Bad Request")
            u = users.get_user_by_sub(sub_claim)
            if not u:
                return _json(start_response, {"error": "user_unknown"}, "404 Not Found")
            allowed = str(u.username).strip().lower().replace("_", "-")
            if label != allowed:
                return _json(start_response, {"error": "label_must_match_username"}, "403 Forbidden")
            nc_client = client_from_config(config.load_config())
            if not nc_client:
                return _json(start_response, {"error": "namecheap_not_configured"}, "503 Service Unavailable")
            apex = str(config.namecheap_section().get("apex_domain") or "nodeadline.online")
            nc_sec = config.namecheap_section()
            ingress = str(nc_sec.get("server_ipv4") or "").strip()
            if not ingress:
                return _json(start_response, {"error": "namecheap_server_ipv4_required"}, "503 Service Unavailable")
            fqdn = f"{label}.{apex}"
            prev = dns_registry.get_binding(sub_claim)
            prev_ing = str(prev.get("ingress_ipv4") or "").strip() if prev else ""
            unchanged = bool(
                prev
                and str(prev.get("wan_ipv4") or "").strip() == wan
                and str(prev.get("fqdn") or "").strip() == fqdn
                and int(prev.get("public_port") or 0) == public_port
                and prev_ing == ingress
            )
            if not unchanged:
                try:
                    # A → IP ingress (VPS); TLS и прокси на WAN:порт ноды настраивает nginx.
                    nc_client.set_hosts_merged(domain=apex, subdomain=label, address=ingress, ttl=300)
                except NamecheapError as e:
                    return _json(start_response, {"ok": False, "error": str(e)[:300]}, "502 Bad Gateway")
            dns_registry.upsert_binding(
                sub=sub_claim,
                username=str(u.username),
                email=str(u.email or ""),
                wan_ipv4=wan,
                fqdn=fqdn,
                public_port=public_port,
                ingress_ipv4=ingress,
            )
            ok_ngx, ngx_err = nginx_ingress.rebuild_map_and_reload()
            if not ok_ngx:
                return _json(
                    start_response,
                    {"ok": False, "error": "nginx_ingress_reload_failed", "detail": ngx_err[:400]},
                    "502 Bad Gateway",
                )
            public_https_url = f"https://{fqdn}/"
            return _json(start_response, {
                "ok": True,
                "fqdn": fqdn,
                "wan_ipv4": wan,
                "public_port": public_port,
                "ingress_ipv4": ingress,
                "public_https_url": public_https_url,
                "unchanged": unchanged,
            })

        if path == "/bt/announce":
            body = tracker.announce(qs, remote)
            start_response("200 OK", [
                ("Content-Type", "text/plain"),
                ("Content-Length", str(len(body))),
            ])
            return [body]

        if path == "/api/torrent/v1/register" and method == "POST":
            try:
                data = json.loads(_read_body(environ))
            except json.JSONDecodeError:
                return _text(start_response, "Bad JSON", "400 Bad Request")
            tracker.register_content(
                infohash_hex=str(data.get("infohash", "")).lower(),
                owner_sub=str(data.get("owner_sub", "")),
                share_id=str(data.get("share_id", "")),
                file_count=int(data.get("file_count", 0)),
                total_bytes=int(data.get("total_bytes", 0)),
                snapshot_revision=int(data.get("snapshot_revision", 0)),
            )
            return _json(start_response, {"ok": True})

        if path == "/api/torrent/v1/list" and method == "GET":
            params = parse_qs(qs)
            owner = (params.get("owner_sub") or [None])[0]
            return _json(start_response, tracker.list_content(owner))

        parts = path.strip("/").split("/")
        if len(parts) == 1 and parts[0] and not parts[0].startswith("api"):
            u = users.get_user_by_username(parts[0])
            if u:
                rh = (environ.get("HTTP_HOST") or "").split(":")[0].strip().lower()
                ap = str(config.namecheap_section().get("apex_domain") or "nodeadline.online").strip().lower()
                sl = _subdomain_label(rh, ap)
                if sl and parts[0].lower() == sl:
                    for bb in dns_registry.load_all_bindings().values():
                        if str(bb.get("fqdn") or "").strip().lower() != rh:
                            continue
                        if is_hosted_binding(bb):
                            return _redirect(start_response, "/site/")
                        break
                if method in ("GET", "HEAD") and not _wants_json_profile(environ, qs):
                    page = _user_cabinet_html(u, dns_registry.get_binding(u.google_sub))
                    return _html(start_response, page, head_only=(method == "HEAD"))
                return _json(start_response, u.to_dict())
            return _text(start_response, "User not found", "404 Not Found")

        return _text(start_response, "Not Found", "404 Not Found")

    except Exception:
        log.exception("error %s %s", method, path)
        return _text(start_response, traceback.format_exc(), "500 Internal Server Error")


def _oauth_start(environ, start_response, qs):
    params = parse_qs(qs)
    return_to = (params.get("return_to") or [""])[0].strip()
    if return_to and not delegated.allowed_return_to(return_to):
        return _text(start_response, "Forbidden return_to", "403 Forbidden")
    cid, _ = config.google_creds()
    if not cid:
        return _text(start_response, "OAuth not configured", "500 Internal Server Error")
    st = secrets.token_urlsafe(24)
    _OAUTH_STATES[st] = {"return_to": return_to, "created_at": int(time.time())}
    redir = f"{config.callback_base()}/oauth/google/callback"
    url = oauth_google.build_google_auth_url(client_id=cid, redirect_uri=redir, state=st)
    return _redirect(start_response, url)


def _oauth_cb(environ, start_response, qs):
    params = parse_qs(qs)
    code = (params.get("code") or [""])[0]
    st = (params.get("state") or [""])[0]
    err = (params.get("error") or [""])[0]
    if err:
        return _text(start_response, f"OAuth error: {err}", "400 Bad Request")
    sd = _OAUTH_STATES.pop(st, None)
    if not sd or int(time.time()) - sd["created_at"] > _OAUTH_TTL:
        return _text(start_response, "Invalid state", "400 Bad Request")
    cid, csec = config.google_creds()
    redir = f"{config.callback_base()}/oauth/google/callback"
    tok = oauth_google.exchange_code(code=code, client_id=cid, client_secret=csec, redirect_uri=redir)
    at = tok.get("access_token", "")
    if not at:
        return _text(start_response, "No access_token", "400 Bad Request")
    info = oauth_google.fetch_userinfo(at)
    sub = info.get("sub", "")
    if not sub:
        return _text(start_response, "No sub", "400 Bad Request")
    email = info.get("email", "")
    name = info.get("name", "")
    pic = info.get("picture", "")
    uname = oauth_google.normalize_username(email)
    user = users.upsert_user(sub=sub, email=email, name=name, picture=pic, username=uname)
    try:
        ensure_hosted_subdomain_after_oauth(sub)
    except Exception:
        log.exception("ensure_hosted_subdomain_after_oauth")
    ret = sd.get("return_to", "")
    if ret and delegated.allowed_return_to(ret):
        rc = delegated.generate_redeem_code(sub=sub, email=email, name=name, picture=pic)
        sep = "&" if "?" in ret else "?"
        return _redirect(start_response, f"{ret}{sep}redeem_code={rc}")
    headers: list[tuple[str, str]] = []
    _set_cookie(headers, {
        "sub": sub,
        "email": email,
        "username": user.username,
        "exp": int(time.time()) + session.SESSION_TTL,
    })
    headers += [("Location", f"/{user.username}/"), ("Content-Length", "0")]
    start_response("302 Found", headers)
    return [b""]


def main():
    import waitress

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8765"))

    if os.environ.get("NODEADLINE_MASTER_ALLOW_MULTIPLE", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        from libs.system.master_cleanup import terminate_other_master_instances

        killed = terminate_other_master_instances(_ROOT, port)
        if killed:
            log.info("master singleton: завершены другие процессы master (PORT=%s): %s", port, killed)
    users.set_data_dir(os.path.join(_ROOT, "data"))
    os.makedirs(os.path.join(_ROOT, "data"), exist_ok=True)
    log.info("master on %s:%d", host, port)
    waitress.serve(application, host=host, port=port, _quiet=True)


if __name__ == "__main__":
    main()
