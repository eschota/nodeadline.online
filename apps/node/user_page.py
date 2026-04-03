"""Дашборд ноды: тёплый светлый UI, ручной стиль, SVG-иконки."""

from __future__ import annotations

import html as html_mod
import json
import os
from typing import Any
from urllib.parse import quote

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _default_windows_installer_href() -> str:
    """Ссылка на .exe с мастера: приоритет public/version.json, иначе стабильное имя в /downloads/."""
    p = os.path.join(_REPO_ROOT, "public", "version.json")
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f)
        u = v.get("url")
        if isinstance(u, str) and u.startswith("http"):
            return u
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return "https://nodeadline.online/downloads/nodeadline-installer-windows-amd64.exe"


def _esc(s: str) -> str:
    return html_mod.escape(s, quote=True)


# Иконки «от руки»: неровные линии, stroke-linecap round
SVG_LOGO = """<svg class="ico-svg" xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32" aria-hidden="true"><path d="M6 20c2-8 10-14 18-10 4 2 6 8 3 12-3 5-11 4-15-1" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="22" cy="10" r="3" fill="currentColor" opacity=".85"/></svg>"""

SVG_WIN = """<svg class="ico-svg" xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5l8-1v9H6V5zm0 10h8v9l-8-1.2V15zm9-11l7-1v10h-7V4zm0 11h7v10l-7-1.1V15z" fill="currentColor"/></svg>"""

TOKENS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;800&family=Nunito:wght@400;600;700&family=Caveat:wght@600&display=swap');
:root{
  --bg:#faf7f2;--bg2:#f3ece3;--fg:#1c1917;--muted:#78716c;
  --card:#fffdfb;--stroke:#292524;--border:rgba(41,37,36,.12);
  --accent:#c2410c;--accent-ink:#fff7ed;--ok:#15803d;--warn:#ca8a04;--err:#b91c1c;
  --shadow:3px 4px 0 rgba(28,25,23,.07);
  --glass:rgba(255,253,251,.78);--glass-line:rgba(255,255,255,.55);
}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;font-family:'Nunito',system-ui,sans-serif;background:var(--bg);color:var(--fg);
  background-image:radial-gradient(ellipse 80% 50% at 50% -10%,#fde68a22,transparent)}
.wrap{max-width:42rem;margin:0 auto;padding:1.5rem 1rem 3rem;position:relative}
.stickers{position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:0}
.sticker{position:absolute;font-family:'Caveat',cursive;font-size:1.05rem;font-weight:600;padding:.35rem .65rem;border:2px solid var(--stroke);
  border-radius:4px 12px 8px 14px;box-shadow:3px 3px 0 rgba(28,25,23,.12),inset 0 1px 0 var(--glass-line);transform:rotate(-6deg)}
.sticker.s1{top:.5rem;right:.2rem;background:#fde68a;color:#713f12;z-index:1}
.sticker.s2{top:5.2rem;left:-.2rem;background:#bae6fd;color:#0c4a6e;transform:rotate(8deg);z-index:1}
.sticker.s3{bottom:8rem;right:0;background:#fecaca;color:#7f1d1d;transform:rotate(-4deg);z-index:1}
.wrap>.head-row,.wrap>.verline,.wrap>.sub,.wrap>.net-banner,.wrap>.hand-card,.wrap>.net-card{position:relative;z-index:2}
#toast-host{position:fixed;bottom:1rem;left:50%;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:.45rem;align-items:center;max-width:min(92vw,24rem);pointer-events:none}
.toast{pointer-events:auto;padding:.55rem .95rem;border-radius:10px 14px 8px 12px;border:2px solid var(--stroke);font-size:.82rem;font-weight:700;
  box-shadow:0 10px 40px rgba(28,25,23,.18),4px 4px 0 rgba(28,25,23,.1);animation:toastIn .28s ease-out;backdrop-filter:blur(10px)}
.toast-info{background:var(--glass);color:var(--fg)}
.toast-success{background:#dcfce7;color:#14532d;border-color:#166534}
.toast-warn{background:#fef9c3;color:#713f12;border-color:#a16207}
.toast-err{background:#fee2e2;color:#7f1d1d;border-color:#991b1b}
.toast-out{opacity:0;transform:translateY(6px);transition:opacity .25s,transform .25s}
@keyframes toastIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.lottie-overlay{position:fixed;inset:0;z-index:9998;display:flex;align-items:center;justify-content:center;background:rgba(28,25,23,.35);
  backdrop-filter:blur(6px);padding:1rem}
.lottie-overlay[hidden]{display:none!important}
.lottie-overlay-inner{text-align:center;padding:1.25rem 1.5rem;border-radius:16px 12px 20px 14px;border:2px solid var(--stroke);
  background:linear-gradient(165deg,rgba(255,253,251,.92),rgba(253,250,245,.88));box-shadow:0 24px 64px rgba(28,25,23,.2),inset 0 1px 0 rgba(255,255,255,.6)}
#lottie-success-wrap{width:200px;height:200px;margin:0 auto}
.lottie-overlay-msg{margin:.5rem 0 0;font-weight:700;font-size:.95rem;color:var(--ok)}
h1{font-family:'Caveat',cursive;font-size:2.1rem;font-weight:600;margin:0;letter-spacing:.02em;color:var(--stroke)}
.head-row{display:flex;align-items:center;gap:.65rem;margin-bottom:.15rem}
.head-row .ico-svg{color:var(--accent)}
.sub{color:var(--muted);font-size:.82rem;margin:0 0 1rem}
.verline{font-size:.85rem;color:var(--muted);font-family:ui-monospace,monospace;margin:.35rem 0 0;letter-spacing:.02em}
.ico-svg{display:inline-block;vertical-align:middle}
.ico-sm{opacity:.9}

.hand-card{border:2px solid var(--stroke); border-radius:10px 18px 12px 14px; background:var(--glass); backdrop-filter:blur(14px);
  box-shadow:var(--shadow),0 12px 40px rgba(28,25,23,.06),inset 0 1px 0 var(--glass-line); padding:1rem 1.1rem; margin-bottom:1rem}
.hand-card h2{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 .65rem;font-weight:700}
.status{font-size:.84rem;color:var(--muted);line-height:1.55}
.status b{color:var(--fg)}
.btn{font:inherit;font-size:.78rem;font-weight:700;padding:.45rem .9rem;border-radius:10px 14px 8px 12px;border:2px solid var(--stroke);
  background:var(--card);color:var(--fg);cursor:pointer;margin-right:.4rem;margin-bottom:.4rem;box-shadow:2px 2px 0 rgba(28,25,23,.12)}
.btn:hover{transform:translate(-1px,-1px);box-shadow:3px 3px 0 rgba(28,25,23,.15)}
.btn:disabled{opacity:.65;cursor:not-allowed;transform:none}
.btn-loading{position:relative;padding-left:1.85rem}
.btn-loading::before{content:"";position:absolute;left:.55rem;top:50%;width:.85rem;height:.85rem;margin-top:-.425rem;border:2px solid rgba(41,37,36,.25);
  border-top-color:var(--stroke);border-radius:50%;animation:spin .7s linear infinite}
.btn-primary.btn-loading::before{border-top-color:rgba(255,247,237,.85);border-color:rgba(255,247,237,.25)}
.net-actions .link.btn-loading::before{border-top-color:var(--accent);border-color:rgba(194,65,12,.2)}
@keyframes spin{to{transform:rotate(360deg)}}
.btn-primary{background:var(--accent);color:var(--accent-ink);border-color:var(--stroke)}
.row{display:flex;flex-wrap:wrap;gap:.35rem;align-items:center}
.input{font:inherit;font-size:.8rem;padding:.45rem .65rem;border-radius:8px 12px;border:2px solid var(--stroke);background:#fff;color:var(--fg);min-width:8rem}
.list{font-size:.8rem}
.item{display:flex;justify-content:space-between;align-items:flex-start;padding:.45rem 0;border-bottom:1px dashed var(--border);gap:.5rem}
.item:last-child{border-bottom:none}
.meta{font-size:.72rem;color:var(--muted)}
.pill{display:inline-block;padding:.15rem .45rem;border-radius:8px 12px;font-size:.68rem;font-weight:700;background:var(--bg2);border:1px solid var(--border)}

.net-card{border:2px solid var(--stroke); border-radius:14px 10px 18px 12px; padding:1rem 1.1rem;
  background:linear-gradient(165deg,rgba(255,255,255,.95) 0%,rgba(255,251,247,.88) 100%);backdrop-filter:blur(12px);
  box-shadow:var(--shadow),0 16px 48px rgba(28,25,23,.07),inset 0 1px 0 rgba(255,255,255,.65); margin-bottom:1rem}
.net-head{display:flex;align-items:flex-start;gap:.85rem}
.net-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;margin-top:.4rem;border:2px solid var(--stroke)}
.net-dot.ok{background:var(--ok);box-shadow:0 0 0 3px rgba(21,128,61,.2)}
.net-dot.warn{background:var(--warn)}
.net-dot.idle{background:#d6d3d1}
.net-title{font-size:.95rem;font-weight:700;margin:0;letter-spacing:-.02em;color:var(--fg)}
.net-sub{font-size:.78rem;color:var(--muted);margin:.35rem 0 0;line-height:1.45;max-width:28rem}
.net-url{font-family:ui-monospace,monospace;font-size:.78rem;color:var(--ok);margin:.45rem 0 0;word-break:break-all;font-weight:600}
.net-actions{margin-top:.65rem;display:flex;flex-wrap:wrap;gap:.4rem;align-items:center}
.net-actions .link{background:none;border:none;color:var(--accent);font-size:.78rem;font-weight:600;cursor:pointer;text-decoration:underline;text-underline-offset:3px;padding:0}
details.net-man{margin-top:.75rem;border-top:1px dashed var(--border);padding-top:.65rem}
details.net-man summary{cursor:pointer;font-size:.72rem;color:var(--muted);letter-spacing:.04em;font-weight:700;list-style:none}
details.net-man summary::-webkit-details-marker{display:none}
.net-man-body{margin-top:.55rem;display:flex;flex-wrap:wrap;gap:.45rem;align-items:center}
.port-local-head{display:flex;align-items:center;justify-content:space-between;gap:.75rem;margin-bottom:.75rem;padding-bottom:.65rem;border-bottom:1px dashed var(--border)}
.port-word-sm{font-family:Inter,system-ui,sans-serif;font-size:1.05rem;font-weight:900;letter-spacing:.2em;background:linear-gradient(135deg,#1c1917,#78716c);-webkit-background-clip:text;background-clip:text;color:transparent}
.net-port-pill{font-family:ui-monospace,monospace;font-size:.78rem;font-weight:800;padding:.3rem .65rem;border-radius:999px;border:2px solid var(--border);background:var(--bg2)}
.net-port-pill.ok{color:#14532d;background:#dcfce7;border-color:#166534}
.net-port-pill.warn{color:#854d0e;background:#fef9c3;border-color:#ca8a04}
.net-port-pill.idle{color:var(--muted);background:#f5f5f4}
.net-man-panel{background:rgba(255,255,255,.55);border-radius:12px;padding:.75rem .85rem;margin-top:.5rem;border:1px solid var(--border)}

.net-banner{font-size:.76rem;color:var(--muted);border:2px dashed var(--stroke);border-radius:12px;padding:.6rem .85rem;margin:0 0 1rem;line-height:1.45;background:var(--bg2)}
.net-banner a{color:var(--accent);font-weight:700;font-family:ui-monospace,monospace;font-size:.72rem}

.dl-strip{display:flex;align-items:flex-start;gap:.85rem}
.dl-strip .ico-wrap{color:var(--accent);flex-shrink:0}
.dl-title{font-weight:700;font-size:.9rem;margin:0 0 .4rem}
.dl-links{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}
.dl-links a{font-weight:700;color:var(--accent);text-decoration:underline;text-underline-offset:3px;font-size:.9rem}
.edge-badge{display:inline-block;font-weight:800;font-size:.8rem;padding:.35rem .65rem;border-radius:8px 14px 10px 12px;
  background:linear-gradient(145deg,#ea580c,#c2410c);color:#fff;box-shadow:2px 2px 0 rgba(28,25,23,.2);border:2px solid var(--stroke);letter-spacing:.02em}
.edge-badge.mute{background:#e7e5e4;color:var(--muted);border-color:#d6d3d1}
.oauth-card{border:3px solid var(--stroke);border-radius:12px 18px 14px 16px;padding:1rem 1.15rem 1.15rem;
  background:linear-gradient(155deg,#fff7ed 0%,#ffedd5 45%,#fffdfb 100%);box-shadow:0 14px 44px rgba(194,65,12,.12),4px 4px 0 rgba(28,25,23,.08),inset 0 1px 0 #fff}
.oauth-card h2{color:var(--accent);font-size:.85rem}
.oauth-card .oauth-lead{font-size:.88rem;line-height:1.55;margin:0 0 .75rem}
.oauth-card .btn-primary{font-size:.85rem;padding:.55rem 1.1rem;box-shadow:0 4px 16px rgba(194,65,12,.35)}
"""


def _net_tier(d: dict[str, Any]) -> str:
    probe = str(d.get("public_probe_status") or "")
    wan, pub = d.get("wan_ip"), d.get("public_port")
    if probe == "reachable":
        return "ok"
    if wan and pub:
        if probe == "unreachable":
            return "warn"
        return "ok"
    return "idle"


def _format_net_html(d: dict[str, Any]) -> str:
    tier = _net_tier(d)
    dot = "ok" if tier == "ok" else ("warn" if tier == "warn" else "idle")
    wan, pub = d.get("wan_ip"), d.get("public_port")

    if tier == "ok":
        title = "В сети"
        sub = "Роутер пробрасывает порт на этот компьютер."
    elif tier == "warn":
        title = "С ограничениями"
        sub = "Проверка с мастера не прошла — проверь внешний порт в блоке ниже (он часто не совпадает с локальным), затем «Сохранить и проверить»."
    else:
        title = "Только локально"
        sub = "Пока нет доступа из интернета — только с этого ПК."

    parts = [
        '<div class="net-head">',
        f'<span class="net-dot {dot}" title=""></span><div>',
        f'<p class="net-title">{_esc(title)}</p>',
        f'<p class="net-sub">{_esc(sub)}</p>',
    ]
    if wan and pub:
        parts.append(f'<p class="net-url">{_esc(f"http://{wan}:{int(pub)}/")}</p>')
    parts.append("</div></div>")
    return "".join(parts)


def render_page(
    *,
    session: dict[str, Any] | None,
    username: str | None,
    runtime_dir: str,
    node_version: str,
    initial_net: dict[str, Any],
    loopback: bool = True,
) -> str:
    owner = session is not None
    can_port = owner or loopback
    name = ""
    if session:
        name = session.get("username") or session.get("email") or ""

    inst_build = ""
    try:
        with open(os.path.join(runtime_dir, "installer_build.txt"), encoding="utf-8") as f:
            inst_build = f.read().strip()
    except OSError:
        pass
    ver_bits = []
    if node_version:
        ver_bits.append(f"узел v{node_version}")
    if inst_build:
        ver_bits.append(f"сборка {inst_build}")
    ver_html = (
        f'<p id="verline" class="verline">{" · ".join(ver_bits)}</p>' if ver_bits else '<p id="verline" class="verline"></p>'
    )

    _pp = int(initial_net.get("public_port") or 0)
    pubp_attr = f' value="{_pp}"' if _pp else ""
    _wan = str(initial_net.get("wan_ip") or "").strip()
    wan_attr = f' value="{_esc(_wan)}"' if _wan else ""
    _lp = int(initial_net.get("listen_port") or 0)

    nt = _net_tier(initial_net)
    pill_cls = "ok" if nt == "ok" else ("warn" if nt == "warn" else "idle")
    pill_txt = str(int(initial_net["public_port"])) if initial_net.get("public_port") else "—"
    net_actions = ""
    if can_port:
        net_actions = f"""
        <div class="net-actions">
          <button type="button" id="btn-recheck" class="link" onclick="recheckNet()">Проверить доступность снаружи</button>
        </div>
        <details class="net-man" id="net-man" open>
          <summary>Публичный адрес · WAN и порт</summary>
          <div class="net-man-body net-man-panel">
            <p class="meta" style="margin:0;width:100%">Если проброс на роутере другой порта — укажи WAN и внешний порт здесь, затем «Сохранить».</p>
            <input class="input" id="wanip" type="text" inputmode="decimal" autocomplete="off" placeholder="WAN IP"{wan_attr}/>
            <input class="input" id="pubp" type="number" min="1" max="65535" placeholder="Порт снаружи"{pubp_attr}/>
            <button class="btn btn-primary" id="btn-manual-save" type="button" onclick="manualPort()">Сохранить и проверить</button>
          </div>
        </details>"""
    else:
        net_actions = (
            '<p class="meta" style="margin:.5rem 0 0;font-size:.72rem">Порт можно менять с этого компьютера '
            '(<a href="http://127.0.0.1:' + str(_lp) + '/">127.0.0.1</a>) или после входа в аккаунт.</p>'
            if _lp
            else '<p class="meta" style="margin:.5rem 0 0;font-size:.72rem">Порт можно менять с localhost или после входа.</p>'
        )

    network_card = f"""
        <div class="net-card">
        <div class="port-local-head">
          <span class="port-word-sm">PORT</span>
          <span id="net-port-pill" class="net-port-pill {pill_cls}">{_esc(pill_txt)}</span>
        </div>
        <div id="net">{_format_net_html(initial_net)}</div>
        {net_actions}
        </div>"""

    stats_card = """
        <div class="hand-card"><h2>Статистика</h2>
        <div id="dash-stats" class="status">…</div>
        <p class="meta" style="margin-top:.5rem">Скачано — объём с мастера по каналу <code>/site/</code>. Раздача (upload) между пирами по BitTorrent в этой сборке не считается; для шаров — только announce на трекер и снимки.</p>
        </div>"""

    ext_banner = ""
    if not loopback and _lp:
        ext_banner = (
            f'<div class="net-banner">Управление и вход — на этом компьютере: '
            f'<a href="http://127.0.0.1:{_lp}/?local=1">http://127.0.0.1:{_lp}/?local=1</a></div>'
        )

    _win_dl = _esc(_default_windows_installer_href())
    dl_block = f"""
        <div class="hand-card" id="dl-card">
          <h2>Скачать установщик</h2>
          <div class="dl-strip">
            <div class="ico-wrap">{SVG_WIN}</div>
            <div style="flex:1;min-width:0">
              <p class="dl-title">Windows (64-bit)</p>
              <div class="dl-links">
                <a id="dl-win" href="{_win_dl}">Скачать .exe</a>
                <span id="edge-badge" class="edge-badge mute">сервер…</span>
              </div>
              <p class="meta" style="margin:.5rem 0 0">Актуальная версия с сервера nodeadline.online — см. бейдж.</p>
              <p class="meta" style="margin:.45rem 0 0">Статический канал с мастера (синхронизация): <a href="/site/">/site/</a></p>
            </div>
          </div>
        </div>"""

    login = ""
    if not owner:
        login = """
        <div class="hand-card oauth-card"><h2>Войти через Google (почта)</h2>
        <p class="oauth-lead status">Папки, <b>синхронизация (торрент)</b> и настройки — после входа через Google <b>с этого ПК</b>. Блок PORT выше можно менять <b>без входа</b>. Ниже — только публичные превью.</p>
        <a class="btn btn-primary" href="/oauth/start" style="display:inline-block;text-decoration:none">Войти через Google</a>
        </div>"""

    owner_block = ""
    if owner:
        owner_block = f"""
        <div class="hand-card"><h2>В двух словах</h2>
        <ol class="status" style="margin:0;padding-left:1.15rem;line-height:1.55">
          <li><b>Сеть</b> — зелёный = порт есть; ручной режим только если пробросил сам.</li>
          <li><b>Папки</b> — путь на диске и короткое имя в ссылке.</li>
          <li><b>Синк</b> — после индекса нажми «Снимок», чтобы трекер увидел шар.</li>
        </ol>
        <p class="meta" style="margin:.65rem 0 0">Публичная витрина — только помеченные папки; открыть <code>/p/&lt;slug&gt;/</code> из списка файлов.</p></div>

        <div class="hand-card"><h2>Аккаунт</h2><p class="status"><b>{_esc(name)}</b></p>
        <button class="btn" onclick="fetch('/api/logout',{{method:'POST'}}).then(()=>location.reload())">Выйти</button></div>

        <div class="hand-card"><h2>Папки</h2><div id="shares" class="list">…</div>
        <div class="row" style="margin-top:.5rem">
          <input class="input" id="lp" placeholder="Полный путь к папке на этом ПК" style="flex:1;min-width:12rem"/>
          <input class="input" id="mp" placeholder="Имя в URL"/>
          <button class="btn" onclick="pickFolder()" title="Системный диалог выбора папки">Выбрать папку…</button>
          <button class="btn btn-primary" onclick="addShare()">Добавить</button>
        </div>
        <p class="meta" style="margin-top:.5rem">«Выбрать папку» открывает диалог ОС. «Добавить» регистрирует шар. «Файлы» — список и скачивание.</p></div>

        <div class="hand-card"><h2>Файлы</h2><div id="ex" class="status">Выбери шар и нажми «Файлы».</div></div>

        <div class="hand-card"><h2>Синхронизация</h2><div id="tor" class="status">…</div>
        <p class="meta" style="margin-top:.5rem">Трекер и снимок: публикация даёт infohash для пиров.</p></div>

        <div class="hand-card"><h2>Медиа</h2><div id="med" class="status">…</div>
        <p class="meta" style="margin-top:.5rem">ffmpeg по желанию — превью после сканирования.</p></div>

        <div class="hand-card"><h2>Диагностика</h2>
        <button class="btn" onclick="copyDiag()">Копировать JSON</button>
        <pre id="diag" class="status" style="margin-top:.5rem;white-space:pre-wrap;font-size:.72rem"></pre></div>
        """

    public = """
        <div class="hand-card"><h2>Публичные папки</h2>
        <p class="meta" style="margin:0 0 .5rem">То, что владелец пометил публичным; вход не нужен. Синхронизация между устройствами — у владельца после входа (снимок → трекер).</p>
        <div id="pubs" class="list">…</div></div>"""

    scripts = """
<script>
const IS_OWNER=document.body.dataset.owner==="1";
const CAN_PORT=document.body.dataset.canPort==="1";
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function toast(msg,kind){
  const host=document.getElementById('toast-host');if(!host||!msg)return;
  const t=document.createElement('div');t.className='toast toast-'+(kind||'info');t.setAttribute('role','status');t.textContent=msg;
  host.appendChild(t);setTimeout(()=>{t.classList.add('toast-out');setTimeout(()=>t.remove(),280)},4000);
}
async function fetchJson(url,opts){
  const r=await fetch(url,opts||{});
  let data=null;const ct=r.headers.get('content-type')||'';
  if(ct.includes('application/json')){try{data=await r.json();}catch(e){data=null;}}
  else{try{data=await r.text();}catch(e){data=null;}}
  if(!r.ok){
    const err=(data&&typeof data==='object'&&data.error!=null)?String(data.error):(r.statusText||'Ошибка '+r.status);
    const e=new Error(err);e.status=r.status;e.body=data;throw e;
  }
  if(data&&typeof data==='object'&&data.ok===false&&data.error){throw new Error(String(data.error));}
  return data;
}
async function j(u,o){return fetchJson(u,o)}
function post(u){return fetchJson(u,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}
let _lottieAnim=null;
async function showLottieSuccess(){
  const overlay=document.getElementById('lottie-overlay');
  const wrap=document.getElementById('lottie-success-wrap');
  if(!overlay||!wrap)return;
  overlay.hidden=false;wrap.innerHTML='';
  try{
    const mod=await import('https://esm.sh/lottie-web@5.12.2');
    const lottie=mod.default;
    _lottieAnim=lottie.loadAnimation({container:wrap,renderer:'svg',loop:false,autoplay:true,path:'/assets/lottie/success.json'});
    await new Promise(r=>setTimeout(r,1900));
  }catch(e){
    toast('Анимация недоступна','warn');
    await new Promise(r=>setTimeout(r,600));
  }
  overlay.hidden=true;if(_lottieAnim){try{_lottieAnim.destroy();}catch(e){}_lottieAnim=null;}
}
const p=new URLSearchParams(location.search);
if(p.get("local")==="1")sessionStorage.setItem("nodeadline_skip_pub_redirect","1");
function netTier(d){
  const pr=String(d.public_probe_status||"");
  const wan=d.wan_ip,pub=d.public_port;
  if(pr==="reachable")return "ok";
  if(wan&&pub){if(pr==="unreachable")return "warn";return "ok";}
  return "idle";
}
function publicUrl(d){
  if(!d.wan_ip||!d.public_port)return null;
  return "http://"+String(d.wan_ip)+":"+String(d.public_port)+"/";
}
function renderNetInner(d){
  const t=netTier(d);
  const dot=t==="ok"?"ok":t==="warn"?"warn":"idle";
  let title="Только локально",sub="Пока нет доступа из интернета — только с этого ПК.";
  if(t==="ok"){title="В сети";sub="Роутер пробрасывает порт на этот компьютер.";}
  if(t==="warn"){title="С ограничениями";sub="Проверка с мастера не прошла — уточни внешний порт ниже (часто ≠ локальному), потом «Сохранить и проверить».";}
  let h='<div class="net-head"><span class="net-dot '+dot+'"></span><div>';
  h+='<p class="net-title">'+esc(title)+'</p><p class="net-sub">'+esc(sub)+'</p>';
  const u=publicUrl(d);
  if(u)h+='<p class="net-url">'+esc(u)+'</p>';
  h+='</div></div>';
  return h;
}
function updateNetPill(d){
  const pill=document.getElementById('net-port-pill');
  if(!pill)return;
  const t=netTier(d);
  const pub=d.public_port;
  pill.textContent=(pub!=null&&pub!=="")?String(pub):"—";
  pill.className='net-port-pill '+(t==="ok"?"ok":t==="warn"?"warn":"idle");
}
function applyNetView(d){
  const el=document.getElementById('net');
  if(el)el.innerHTML=renderNetInner(d);
  updateNetPill(d);
}
function maybeRedirectPublic(d){
  if(sessionStorage.getItem("nodeadline_skip_pub_redirect"))return;
  if(sessionStorage.getItem("nodeadline_pub_redirect_done"))return;
  if(String(d.public_probe_status||"")!=="reachable")return;
  const u=publicUrl(d);
  if(!u)return;
  const h=location.hostname;
  if(h!=="127.0.0.1"&&h!=="localhost")return;
  sessionStorage.setItem("nodeadline_pub_redirect_done","1");
  location.href=u;
}
async function recheckNet(){
  if(!CAN_PORT)return;
  const btn=document.getElementById('btn-recheck');
  if(btn){btn.disabled=true;btn.classList.add('btn-loading');}
  try{
    await fetchJson('/api/port/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d=await loadNet({skipRedirect:true});
    if(d&&String(d.public_probe_status||'')==='reachable'){
      toast('Доступно из интернета','success');
      await showLottieSuccess();
      maybeRedirectPublic(d);
    }else if(d){
      toast('Проверка: порт недоступен снаружи или не настроен','warn');
    }
  }catch(e){
    toast(e.message||'Ошибка проверки','err');
  }finally{
    if(btn){btn.disabled=false;btn.classList.remove('btn-loading');}
  }
}
async function manualPort(){
  if(!CAN_PORT)return;
  const btn=document.getElementById('btn-manual-save');
  if(btn){btn.disabled=true;btn.classList.add('btn-loading');}
  const p=parseInt(document.getElementById('pubp').value)||0;
  const wanEl=document.getElementById('wanip');
  const wan_ip=wanEl?wanEl.value.trim():'';
  const body={public_port:p};
  if(wan_ip)body.wan_ip=wan_ip;
  try{
    const d=await fetchJson('/api/port/manual',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const st=d.state||null;
    if(st)applyNetView(st);
    if(d.probe&&d.probe.reachable){
      toast('Порт доступен из интернета','success');
      await showLottieSuccess();
      if(st)maybeRedirectPublic(st);
    }else{
      toast(d.probe?'Сохранено. Проверка: недоступен снаружи':'Сохранено. Укажите WAN и порт для проверки','warn');
      await loadNet();
    }
  }catch(e){
    toast(e.message||'Не удалось сохранить','err');
  }finally{
    if(btn){btn.disabled=false;btn.classList.remove('btn-loading');}
  }
}
async function loadNet(opts){
  const el=document.getElementById('net');if(!el)return null;
  const skipRedirect=opts&&opts.skipRedirect;
  try{
    let d=await fetchJson('/api/port/status');
    applyNetView(d);
    if(CAN_PORT&&d.wan_ip&&d.public_port){
      const pr=String(d.public_probe_status||"");
      if(pr==="unknown"||pr===""){
        try{
          await fetchJson('/api/port/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
          d=await fetchJson('/api/port/status');
          applyNetView(d);
        }catch(e){toast(e.message||'Ошибка проверки порта','err');}
      }
    }
    if(!skipRedirect)maybeRedirectPublic(d);
    return d;
  }catch(e){
    el.innerHTML='<span style="color:var(--err)">Сеть недоступна</span>';
    updateNetPill({public_probe_status:'',public_port:null,wan_ip:null});
    toast(e.message||'Сеть недоступна','err');
    return null;
  }
}
function fmtBytes(n){
  if(n==null||!isFinite(n)||n<0)return '—';
  if(n<1024)return String(Math.round(n))+' B';
  const u=['KB','MB','GB','TB'];let i=-1;let x=n;
  do{x/=1024;i++;}while(x>=1024&&i<u.length-1);
  return (x>=10||i===0?x.toFixed(0):x.toFixed(1))+' '+u[i];
}
async function loadStats(){
  const el=document.getElementById('dash-stats');if(!el)return;
  try{
    const d=await j('/api/stats/dashboard');
    const s=d.site_channel||{};
    const lt=d.libtorrent_session||{};
    const tr=d.torrent||{};
    const ann=(tr.announce)||{};
    const tk=d.tracker_master||{};
    const lines=[];
    lines.push('<div class="meta"><b>libtorrent</b>: '+(lt.session||'—')+(lt.dht_nodes!=null?' · DHT: '+lt.dht_nodes:'')+(lt.last_error?(' · <span style="color:var(--err)">'+esc(String(lt.last_error))+'</span>'):'')+'</div>');
    lines.push('<div><b>Сайт /site/</b> — рев. '+String(s.revision||0)+(s.active?' <span style="color:var(--ok)">✓</span>':' <span style="color:var(--muted)">не активен</span>')+' (синк по BT + web seed)</div>');
    lines.push('<div>Скачано с мастера: <b>'+fmtBytes(s.bytes_downloaded_total||0)+'</b> · загрузок: '+(s.download_count||0)+'</div>');
    if(s.last_bundle_bytes)lines.push('<div>Последний бандл: '+fmtBytes(s.last_bundle_bytes)+'</div>');
    lines.push('<div><b>Announce</b> (трекер): успешно <b>'+String(ann.ok||0)+'</b>, ошибок '+String(ann.fail||0)+'</div>');
    if(ann.last_ok_at!=null)lines.push('<div>Последний успешный announce: '+Math.max(0,Math.round(Date.now()/1000-ann.last_ok_at))+' с назад</div>');
    lines.push('<div><b>API трекера на мастере</b>: '+(tk.ok?'<span style="color:var(--ok)">OK</span>':'<span style="color:var(--err)">нет</span>')+(tk.registered_on_master!=null?' · записей в реестре: '+tk.registered_on_master:'')+'</div>');
    if(!tk.ok&&tk.error)lines.push('<div style="color:var(--err)">'+esc(String(tk.error))+'</div>');
    const shares=(tr.shares)||[];
    if(shares.length){
      lines.push('<div style="margin-top:.35rem"><b>Снимки шаров</b></div>');
      shares.forEach(x=>{
        const ih=String(x.infohash||'').slice(0,16);
        const age=x.last_announce_age_sec!=null?(' · '+x.last_announce_age_sec+' с назад'):'';
        lines.push('<div class="meta">— '+esc(String(x.share_id||''))+' · <code>'+esc(ih)+'…</code> rev '+String(x.revision||0)+(x.registered?'':' (не зарегистрирован)')+age+'</div>');
      });
    }else lines.push('<div class="meta"><b>Снимки шаров</b>: пока нет</div>');
    if(tr.peer_wire_accounting===false)lines.push('<div class="meta" style="margin-top:.35rem">Peer-протокол BitTorrent: байты upload/download между пирами не учитываются (только HTTP для /site/ и announce для шаров).</div>');
    el.innerHTML=lines.join('');
  }catch(e){el.innerHTML='<span style="color:var(--err)">'+(e.message||String(e))+'</span>';}
}
async function loadEdgeVersion(){
  const badge=document.getElementById('edge-badge');
  const a=document.getElementById('dl-win');
  if(!badge)return;
  try{
    const d=await j('/api/edge/version');
    if(!d.ok){badge.textContent='нет связи';return;}
    badge.className='edge-badge';
    badge.textContent='v'+d.version+' · '+d.installer_build;
    if(d.windows_url&&a)a.href=d.windows_url;
  }catch(e){
    badge.textContent='ошибка';
  }
}
async function loadShares(){
  const el=document.getElementById('shares');
  if(!el)return;
  let list;
  try{list=await j('/api/shares');}catch(e){return;}
  if(!list.length){el.innerHTML='<span class=meta>Пока пусто — добавь путь выше.</span>';return}
  el.innerHTML=list.map(s=>`<div class=item><div><b>${esc(s.mount_path)}</b><div class=meta>${esc(s.local_path)} · ${s.visibility} · rev ${s.snapshot_revision}</div></div>
    <div class=row><button class=btn onclick="listFiles('${s.share_id}')">Файлы</button>
    <button class=btn onclick="pub('${s.share_id}')">Снимок</button>
    <button class=btn onclick="del('${s.share_id}')">Убрать</button></div></div>`).join('');
}
async function pickFolder(){
  const el=document.getElementById('lp');
  if(!el)return;
  const ph=el.placeholder;
  el.placeholder='Открываю диалог…';
  el.disabled=true;
  const ac=new AbortController();
  const to=setTimeout(()=>ac.abort(),610000);
  try{
    const r=await fetchJson('/api/shares/pick-folder',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:'{}',
      signal:ac.signal
    });
    if(r.path) el.value=r.path;
  }catch(e){
    if(e&&e.name==='AbortError')
      toast('Диалог не ответил за 10 мин — закрой окно и попробуй снова','err');
    else
      toast('Папка: '+(e.message||e),'err');
  }finally{
    clearTimeout(to);
    el.placeholder=ph;
    el.disabled=false;
  }
}
async function addShare(){
  const lp=document.getElementById('lp').value.trim();
  const mp=document.getElementById('mp').value.trim()||'share';
  try{
    await fetchJson('/api/shares',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({local_path:lp,mount_path:mp,visibility:'public'})});
    toast('Шар добавлен','success');
    loadShares();
  }catch(e){toast(e.message||'Ошибка','err');}
}
async function del(id){if(!confirm('Убрать шар?'))return;try{await fetchJson('/api/shares/'+id,{method:'DELETE'});loadShares();}catch(e){toast(e.message||'Ошибка','err');}}
async function pub(id){await post('/api/shares/'+id+'/publish-snapshot');loadShares();loadTor()}
let cur=null;
async function listFiles(id){
  cur=id;
  const d=await j('/api/shares/'+id+'/tree');
  const el=document.getElementById('ex');
  el.innerHTML='<b>Файлы</b><br>'+d.files.map(f=>`<div class=item><span>${esc(f.relative_path)}</span>
    <a class=btn style=text-decoration:none href="/api/shares/${id}/file?path=${encodeURIComponent(f.relative_path)}">Скачать</a></div>`).join('');
}
async function loadPubs(){
  const list=await j('/api/shares/public');
  const el=document.getElementById('pubs');
  if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class=item><b>${esc(s.mount_path)}</b> <a class=btn href="/p/${s.public_slug}/">Открыть</a></div>`).join(''):'<span class=meta>Нет публичных — войди как владелец и добавь.</span>';
}
async function loadTor(){
  const el=document.getElementById('tor');if(!el)return;
  try{
    const t=await j('/api/torrent/status');
    el.innerHTML=t.length?t.map(x=>`<div>${x.share_id} · <code>${x.infohash||'—'}</code> · rev ${x.revision||0}</div>`).join(''):'<span class=meta>Нет снимков</span>';
  }catch(e){el.innerHTML='<span class=meta>—</span>';}
}
async function loadMed(){
  const el=document.getElementById('med');if(!el)return;
  try{
    const s=await j('/api/media/status');
    el.textContent='ffmpeg: '+(s.ffmpeg?'ok':'нет');
  }catch(e){el.textContent='ffmpeg: —';}
}
async function copyDiag(){
  const d=await j('/api/diagnostics');
  document.getElementById('diag').textContent=JSON.stringify(d,null,2);
  navigator.clipboard.writeText(JSON.stringify(d,null,2));
}
async function loadVer(){
  const el=document.getElementById('verline');
  if(!el)return;
  try{
    const d=await j('/api/version');
    const parts=[];
    if(d.node_version)parts.push('узел v'+d.node_version);
    if(d.installer_build)parts.push('сборка '+d.installer_build);
    var srev=d.site_revision;
    var sn=srev!=null&&srev!==''?Number(srev):NaN;
    if(!isNaN(sn)&&(sn>0||d.site_active))parts.push('/site/ rev '+String(sn));
    const line=parts.join(' · ');
    const key='nodeadline_verline';
    const prev=sessionStorage.getItem(key);
    if(prev===null){
      sessionStorage.setItem(key,line);
      el.textContent=line;
      return;
    }
    if(prev!==line){
      sessionStorage.setItem(key,line);
      location.reload();
      return;
    }
    el.textContent=line;
  }catch(e){}
}
setInterval(()=>{loadVer();loadNet();loadStats();loadTor();loadMed()},15000);
document.addEventListener('DOMContentLoaded',()=>{
  loadVer();loadNet();loadStats();loadEdgeVersion();loadShares();loadPubs();loadTor();loadMed();
});
</script>"""

    title = _esc(username or "нода")
    body_attrs = ""
    if owner:
        body_attrs += ' data-owner="1"'
    if loopback:
        body_attrs += ' data-loopback="1"'
    if can_port:
        body_attrs += ' data-can-port="1"'
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>nodeadline — {title}</title><style>{TOKENS}</style></head>
<body{body_attrs}><div id="toast-host" role="status" aria-live="polite" aria-atomic="true"></div>
<div class="lottie-overlay" id="lottie-overlay" hidden>
  <div class="lottie-overlay-inner">
    <div id="lottie-success-wrap"></div>
    <p class="lottie-overlay-msg">Доступно из интернета</p>
  </div>
</div>
<div class="wrap">
<div class="stickers" aria-hidden="true"><span class="sticker s1">Порт</span><span class="sticker s2">Почта</span><span class="sticker s3">Сеть</span></div>
<div class="head-row">{SVG_LOGO}<h1>nodeadline</h1></div>
{ver_html}
<p class="sub">{title}</p>
{ext_banner}
{network_card}
{stats_card}
{dl_block}
{login}{owner_block}{public}
</div>{scripts}</body></html>"""


def render_public_share_page(*, mount: str, slug: str, files: list[dict[str, Any]]) -> str:
    payload = json.dumps({"files": files}, ensure_ascii=False)
    gal_href = f"/p/{quote(slug, safe='')}/gallery"
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_esc(mount)}</title><style>{TOKENS}</style></head>
<body><div class="wrap">
<div class="head-row">{SVG_LOGO}<h1>{_esc(mount)}</h1></div>
<p class="sub">Публичная папка · <a href="{_esc(gal_href)}">Галерея jpg/png</a></p>
<div class="hand-card"><h2>Файлы</h2><div id="f" class="list"></div></div>
</div>
<script>
const T={payload};
document.getElementById('f').innerHTML=T.files.map(f=>'<div class=item><span>'+esc(f.relative_path)+'</span> '+
'<a class=btn href="/p/{_esc(slug)}/file?path='+encodeURIComponent(f.relative_path)+'">Скачать</a></div>').join('');
function esc(s){{const d=document.createElement('div');d.textContent=s;return d.innerHTML}}
</script>
</body></html>"""


def render_public_gallery_page(
    *,
    mount: str,
    slug: str,
    files: list[dict[str, Any]],
    page: int,
    per_page: int,
    total: int,
) -> str:
    base = f"/p/{quote(slug, safe='')}"
    items: list[str] = []
    for f in files:
        rel = str(f.get("relative_path") or "")
        if not rel:
            continue
        orig = f"{base}/file?path={quote(rel, safe='')}"
        # Миниатюра = оригинал (jpg/png); *_poster.jpg может отсутствовать без ffmpeg.
        items.append(
            f'<div class="gal-item"><a href="{_esc(orig)}"><img class="gal-img" src="{_esc(orig)}" alt="" loading="lazy" width="200" height="200"/></a>'
            f'<p class="gal-cap meta">{_esc(rel)}</p></div>'
        )
    total_pages = max(1, (total + per_page - 1) // per_page)
    nav_parts: list[str] = []
    if page > 1:
        nav_parts.append(f'<a class="btn" href="{_esc(base)}/gallery?page={page - 1}">Назад</a>')
    nav_parts.append(f'<span class="meta">стр. {page} / {total_pages} · всего {total}</span>')
    if page < total_pages:
        nav_parts.append(f'<a class="btn" href="{_esc(base)}/gallery?page={page + 1}">Вперёд</a>')
    nav = " ".join(nav_parts)
    gal_style = """
.gal-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:.75rem}
.gal-item{border:1px solid var(--border);border-radius:10px;padding:.45rem;background:var(--card)}
.gal-img{width:100%;height:auto;max-height:280px;object-fit:contain;display:block;border-radius:6px}
.gal-cap{margin:.35rem 0 0;font-size:.68rem;word-break:break-all}
"""
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_esc(mount)} — галерея</title><style>{TOKENS}{gal_style}</style></head>
<body><div class="wrap">
<div class="head-row">{SVG_LOGO}<h1>{_esc(mount)}</h1></div>
<p class="sub"><a href="{_esc(base)}">Все файлы</a> · галерея jpg/png</p>
<div class="hand-card"><h2>Изображения</h2><div class="gal-grid">{"".join(items) or "<p class=meta>Нет подходящих файлов</p>"}</div>
<p class="nav-gal" style="margin-top:1rem">{nav}</p></div>
</div></body></html>"""
