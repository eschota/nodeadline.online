"""Лендинг загрузки: светлая минималистичная вёрстка (карточки платформ, one-liner, копирование)."""

from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))


def _build_stamp_html() -> str:
    """Видимый штамп выкладки — если видишь старый SHA, кэш или не тот сервер."""
    p = os.path.join(_ROOT, "public", "build.json")
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        sha = str(j.get("payload_sha256", "")).strip()
        short = (sha[:14] + "…") if len(sha) > 14 else sha
        bt = str(j.get("built_at_utc", "")).strip()
        return (
            f'<p class="meta-small">Выкладка payload: <code>{short}</code>'
            + (f" · {bt}" if bt else "")
            + ' · <a href="/build.json">build.json</a></p>'
        )
    except OSError:
        return ""


def _download_urls(base: str) -> tuple[str, str, str, str, str]:
    path = os.path.join(_ROOT, "public", "version.json")
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
    except OSError:
        v = {}
    b = base.rstrip("/")
    win = v.get("url") or f"{b}/downloads/nodeadline-installer-windows-amd64.exe"
    linux = v.get("linux_url") or f"{b}/downloads/nodeadline-installer-linux-amd64"
    darwin = v.get("darwin_url") or f"{b}/downloads/nodeadline-installer-darwin-arm64"
    build = str(v.get("installer_build") or "").strip()
    ver = str(v.get("version") or "").strip()
    return win, linux, darwin, build, ver


def core_landing_html(*, base_url: str) -> str:
    b = base_url.rstrip("/")
    win, linux, darwin, build, ver = _download_urls(b)
    script_url = f"{b}/downloads/install-nodeadline-linux.sh"
    curl_line = f"curl -fsSL {script_url} | bash"
    wget_line = f"wget -qO- {script_url} | bash"
    ver_line = ""
    if ver or build:
        bits = []
        if ver:
            bits.append(f"v{ver}")
        if build:
            bits.append(f"build {build}")
        ver_line = f'<p class="sitever">{" · ".join(bits)}</p>'

    # SVG icons (inline)
    ico_win = """<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 5.5L10.2 4.7v7.1H3V5.5zm7.2 8.7H3v7.1l7.2-1V14.2zm1.1-8.9L21 3v8.8h-9.7V5.3zm9.7 9.1H11.3V21L21 19.5v-5.1z"/></svg>"""
    ico_mac = """<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M16.1 4.5c1.4 0 2.5 1 3.4 2.5-.8.5-1.4 1.3-1.4 2.4 0 1.8 1.5 2.6 1.6 2.7-.1.4-.5 1.6-1.4 3.1-.9 1.4-1.8 2.8-3.2 2.8-1.2 0-1.6-.8-3-.8-1.4 0-1.8.8-3 .9-1.3 0-2.3-1.4-3.2-2.8-1.8-3-2.1-6.6-.2-8.1 1-1.2 2.5-1.9 3.8-1.9 1.4 0 2.3.8 3 .8zM16.3 2.2c.1 1.6-1.2 3-2.8 2.8-.2-1.4 1.2-3 2.8-2.8z"/></svg>"""
    ico_linux = """<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm0 2v10h16V7H4zm2 2h2v2H6V9zm3 0h7v2H9V9zm-3 4h4v2H6v-2z"/></svg>"""
    ico_script = """<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11zM8 12.5h8v1.5H8v-1.5zm0 3h5v1.5H8V15.5z"/></svg>"""
    ico_dl = """<svg class="ico ico-dl" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>"""

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>nodeadline</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600;800&display=swap" rel="stylesheet"/>
<style>
:root {{
  --bg:#f8f9fa;--fg:#0a0a0a;--muted:#6c757d;--card:#fff;--border:#e9ecef;--shadow:0 4px 24px rgba(0,0,0,.06);
  --radius:14px;--green:#198754;
}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;font-family:Inter,system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--fg);
  -webkit-font-smoothing:antialiased}}
.wrap{{max-width:36rem;margin:0 auto;padding:2.5rem 1.25rem 3rem}}
h1{{font-size:1.85rem;font-weight:800;letter-spacing:-.03em;margin:0}}
.subtitle{{color:var(--muted);font-size:1rem;margin:.35rem 0 1.75rem;font-weight:500}}
.sitever{{font-size:.8rem;color:var(--muted);margin:-.5rem 0 1.5rem;font-family:ui-monospace,monospace}}
.platforms{{display:grid;grid-template-columns:repeat(4,1fr);gap:.65rem;margin-bottom:1.5rem}}
@media(max-width:520px){{.platforms{{grid-template-columns:repeat(2,1fr)}}}}
.plat{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.4rem;padding:.85rem .5rem;
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);cursor:pointer;font:inherit;
  font-size:.72rem;font-weight:600;color:var(--fg);box-shadow:var(--shadow);transition:transform .15s,border-color .15s,background .15s,color .15s}}
.plat:hover{{transform:translateY(-1px);border-color:#ced4da}}
.plat .ico{{width:22px;height:22px}}
.plat.active{{background:var(--fg);color:#fff;border-color:var(--fg);box-shadow:0 8px 28px rgba(0,0,0,.18)}}
.plat.active .ico{{color:#fff}}
.btn-main{{display:inline-flex;align-items:center;justify-content:center;gap:.55rem;width:100%;padding:1rem 1.25rem;
  background:var(--fg);color:#fff;text-decoration:none;font-weight:600;font-size:.95rem;border-radius:999px;
  border:none;cursor:pointer;box-shadow:0 6px 24px rgba(0,0,0,.2);transition:filter .15s}}
.btn-main:hover{{filter:brightness(1.08)}}
.btn-main .ico-dl{{width:20px;height:20px}}
.oneliner{{margin-top:2rem}}
.oneliner-label{{font-size:.68rem;font-weight:700;letter-spacing:.12em;color:var(--muted);margin:0 0 .75rem}}
.oneliner-label::after{{content:"";display:block;height:1px;background:var(--border);margin-top:.65rem}}
.code-row{{display:flex;gap:.5rem;align-items:stretch;margin-bottom:.65rem}}
.code{{flex:1;background:var(--fg);color:#fff;font-family:ui-monospace,SFMono-Regular,monospace;font-size:.72rem;
  padding:.85rem 1rem;border-radius:10px;line-height:1.45;overflow-x:auto;word-break:break-all}}
.copy-btn{{flex-shrink:0;width:44px;border:1px solid var(--border);border-radius:10px;background:var(--card);cursor:pointer;
  display:flex;align-items:center;justify-content:center;transition:border-color .2s,background .2s}}
.copy-btn:hover{{border-color:#adb5bd}}
.copy-btn.ok{{border-color:var(--green);background:#e8f5e9}}
.copy-btn svg{{width:18px;height:18px;stroke:var(--fg);fill:none;stroke-width:2}}
.copy-btn.ok svg{{stroke:var(--green)}}
footer{{margin-top:2.5rem}}
footer a{{color:var(--fg);font-size:.9rem}}
.hidden{{display:none!important}}
.meta-small{{font-size:.72rem;color:var(--muted);margin-top:1rem;text-align:center}}
.meta-small a{{color:var(--muted)}}
.port-zone{{margin:1.75rem 0 1.5rem}}
.port-head{{display:flex;align-items:baseline;justify-content:space-between;gap:.75rem;margin-bottom:.85rem}}
.port-word{{font-size:1.35rem;font-weight:900;letter-spacing:.18em;background:linear-gradient(135deg,#0a0a0a 0%,#495057 55%,#0a0a0a 100%);-webkit-background-clip:text;background-clip:text;
  color:transparent;text-shadow:0 2px 20px rgba(0,0,0,.06)}}
.port-pill{{font-family:ui-monospace,monospace;font-size:.75rem;font-weight:700;padding:.28rem .65rem;border-radius:999px;background:#fff;border:1px solid var(--border);
  box-shadow:var(--shadow);color:var(--muted)}}
.port-pill.ok{{color:#0f5132;background:#d1e7dd;border-color:#a3cfbb}}
.port-pill.bad{{color:#842029;background:#f8d7da;border-color:#f1aeb5}}
.port-card{{position:relative;border-radius:18px;padding:1.15rem 1.2rem 1.25rem;background:linear-gradient(145deg,#ffffff 0%,#f8f9fa 100%);
  border:1px solid rgba(0,0,0,.06);box-shadow:0 8px 40px rgba(0,0,0,.07),inset 0 1px 0 #fff;overflow:hidden}}
.port-card::before{{content:"";position:absolute;inset:0;border-radius:inherit;padding:1px;background:linear-gradient(135deg,rgba(0,0,0,.12),rgba(0,0,0,.02),rgba(25,135,84,.15));
  -webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);
  -webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none}}
.port-status{{display:flex;align-items:center;gap:.65rem;margin-bottom:1rem;min-height:1.5rem}}
.port-dot{{width:11px;height:11px;border-radius:50%;flex-shrink:0;border:2px solid #dee2e6;background:#e9ecef;transition:background .25s,box-shadow .25s,border-color .25s}}
.port-dot.idle{{background:#e9ecef;border-color:#ced4da}}
.port-dot.ok{{background:#198754;border-color:#146c43;box-shadow:0 0 0 4px rgba(25,135,84,.2);animation:portPulse 1.6s ease-in-out infinite}}
.port-dot.warn{{background:#ffc107;border-color:#cc9a06}}
.port-dot.err{{background:#dc3545;border-color:#b02a37}}
@keyframes portPulse{{0%,100%{{box-shadow:0 0 0 4px rgba(25,135,84,.2)}}50%{{box-shadow:0 0 0 8px rgba(25,135,84,.08)}}}}
.port-status-text{{font-size:.84rem;font-weight:600;color:var(--fg);line-height:1.35}}
.port-status-text.muted{{color:var(--muted);font-weight:500}}
.port-inputs{{display:grid;grid-template-columns:1fr 5.5rem;gap:.55rem;margin-bottom:.75rem}}
@media(max-width:420px){{.port-inputs{{grid-template-columns:1fr}}}}
.port-inp{{width:100%;font:inherit;font-size:.82rem;padding:.62rem .75rem;border-radius:12px;border:1px solid var(--border);background:#fff;
  font-feature-settings:"tnum";transition:border-color .15s,box-shadow .15s}}
.port-inp:focus{{outline:none;border-color:#0a0a0a;box-shadow:0 0 0 3px rgba(0,0,0,.08)}}
.port-inp::placeholder{{color:#adb5bd}}
.port-check-btn{{width:100%;font:inherit;font-size:.82rem;font-weight:700;padding:.72rem 1rem;border-radius:14px;border:2px solid var(--fg);
  background:var(--fg);color:#fff;cursor:pointer;transition:filter .15s,transform .1s}}
.port-check-btn:hover:not(:disabled){{filter:brightness(1.06)}}
.port-check-btn:disabled{{opacity:.55;cursor:not-allowed}}
.port-hint{{font-size:.68rem;color:var(--muted);margin-top:.65rem;line-height:1.4}}
</style>
</head>
<body>
<div class="wrap">
  <h1>nodeadline</h1>
  <p class="subtitle">Установи личную ноду</p>
  {ver_line}
  <div class="platforms" role="tablist" aria-label="Платформа">
    <button type="button" class="plat" data-tab="win" aria-selected="false">{ico_win}Windows</button>
    <button type="button" class="plat" data-tab="mac" aria-selected="false">{ico_mac}macOS</button>
    <button type="button" class="plat" data-tab="linux" aria-selected="false">{ico_linux}Linux</button>
    <button type="button" class="plat active" data-tab="script" aria-selected="true">{ico_script}Script</button>
  </div>

  <section class="port-zone" aria-label="Проверка порта снаружи">
    <div class="port-head">
      <span class="port-word">PORT</span>
      <span class="port-pill" id="port-pill" title="Последняя проверка">—</span>
    </div>
    <div class="port-card">
      <div class="port-status">
        <span class="port-dot idle" id="port-dot" role="img" aria-label="статус"></span>
        <span class="port-status-text muted" id="port-status-text">Введи публичный IP и порт ноды — проверим с сервера nodeadline.</span>
      </div>
      <div class="port-inputs">
        <input type="text" class="port-inp" id="probe-host" inputmode="numeric" autocomplete="off" placeholder="WAN IPv4, напр. 37.192.2.126" />
        <input type="number" class="port-inp port-inp-num" id="probe-port" min="1" max="65535" placeholder="Порт" />
      </div>
      <button type="button" class="port-check-btn" id="btn-probe">Проверить доступность</button>
      <p class="port-hint">TCP с сервера nodeadline до твоего хоста:порта. Зелёный — снаружи открыто; красный — фаервол, NAT или неверный адрес.</p>
    </div>
  </section>

  <a id="main-cta" class="btn-main" href="{script_url}" download>{ico_dl}<span id="cta-text">Скачать install script</span></a>
  <div id="oneliner" class="oneliner">
    <p class="oneliner-label">ONE-LINER</p>
    <div class="code-row">
      <pre class="code" id="line-curl">{curl_line}</pre>
      <button type="button" class="copy-btn" data-copy="line-curl" title="Копировать" aria-label="Копировать curl">
        <svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      </button>
    </div>
    <div class="code-row">
      <pre class="code" id="line-wget">{wget_line}</pre>
      <button type="button" class="copy-btn" data-copy="line-wget" title="Копировать" aria-label="Копировать wget">
        <svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      </button>
    </div>
  </div>
  <p class="meta-small">SHA256: <a href="{b}/downloads/SHA256SUMS">SHA256SUMS</a></p>
  {_build_stamp_html()}
  <footer><a href="/">Home</a> · <a href="{b}/health" style="color:var(--muted)">health</a></footer>
</div>
<script>
(function(){{
  const tabs = document.querySelectorAll('.plat');
  const cta = document.getElementById('main-cta');
  const ctaText = document.getElementById('cta-text');
  const one = document.getElementById('oneliner');
  const urls = {{
    win: {{ href: {json.dumps(win)}, label: 'Скачать установщик Windows', dl: false }},
    mac: {{ href: {json.dumps(darwin)}, label: 'Скачать для macOS', dl: false }},
    linux: {{ href: {json.dumps(linux)}, label: 'Скачать для Linux', dl: false }},
    script: {{ href: {json.dumps(script_url)}, label: 'Скачать install script', dl: true }}
  }};
  function activate(id){{
    tabs.forEach(t => {{
      const on = t.dataset.tab === id;
      t.classList.toggle('active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    }});
    const u = urls[id];
    cta.href = u.href;
    ctaText.textContent = u.label;
    if (u.dl) {{ cta.setAttribute('download', ''); one.classList.remove('hidden'); }}
    else {{ cta.removeAttribute('download'); one.classList.add('hidden'); }}
  }}
  tabs.forEach(t => t.addEventListener('click', () => activate(t.dataset.tab)));
  document.querySelectorAll('.copy-btn').forEach(btn => {{
    btn.addEventListener('click', async () => {{
      const id = btn.getAttribute('data-copy');
      const el = document.getElementById(id);
      const text = el.textContent.trim();
      try {{
        await navigator.clipboard.writeText(text);
        btn.classList.add('ok');
        btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round"/></svg>';
        setTimeout(() => {{
          btn.classList.remove('ok');
          btn.innerHTML = '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
        }}, 2000);
      }} catch(e) {{ alert('Не удалось скопировать'); }}
    }});
  }});
  const PROBE_BASE = {json.dumps(b)};
  (function portProbe(){{
    const hostEl = document.getElementById('probe-host');
    const portEl = document.getElementById('probe-port');
    const dot = document.getElementById('port-dot');
    const txt = document.getElementById('port-status-text');
    const pill = document.getElementById('port-pill');
    const btn = document.getElementById('btn-probe');
    function setDot(state){{
      dot.className = 'port-dot ' + (state || 'idle');
    }}
    function setPill(label, cls){{
      pill.textContent = label;
      pill.className = 'port-pill' + (cls ? ' ' + cls : '');
    }}
    try {{
      const h = localStorage.getItem('nodeadline_probe_host');
      const p = localStorage.getItem('nodeadline_probe_port');
      if (h) hostEl.value = h;
      if (p) portEl.value = p;
    }} catch(e) {{}}
    async function runProbe(){{
      const host = hostEl.value.trim();
      const port = parseInt(portEl.value, 10);
      if (!host || !port || port < 1 || port > 65535) {{
        setDot('warn');
        txt.className = 'port-status-text';
        txt.textContent = 'Нужны IP и порт (1–65535).';
        setPill('—', '');
        return;
      }}
      try {{
        localStorage.setItem('nodeadline_probe_host', host);
        localStorage.setItem('nodeadline_probe_port', String(port));
      }} catch(e) {{}}
      btn.disabled = true;
      setDot('idle');
      txt.className = 'port-status-text muted';
      txt.textContent = 'Проверяем…';
      setPill(host + ':' + port, '');
      try {{
        const url = PROBE_BASE + '/api/public/tcp-probe?host=' + encodeURIComponent(host) + '&port=' + encodeURIComponent(String(port));
        const r = await fetch(url);
        const j = await r.json();
        if (r.status === 429) {{
          setDot('warn');
          txt.className = 'port-status-text';
          txt.textContent = 'Слишком часто — подожди минуту.';
          setPill('лимит', 'bad');
          return;
        }}
        if (!j || j.ok === false) {{
          setDot('err');
          txt.className = 'port-status-text';
          txt.textContent = (j && j.error) ? String(j.error) : 'Ошибка запроса';
          setPill('ошибка', 'bad');
          return;
        }}
        if (j.reachable) {{
          setDot('ok');
          txt.className = 'port-status-text';
          txt.textContent = 'Порт открыт — с nodeadline до тебя TCP проходит.';
          setPill(String(port), 'ok');
        }} else {{
          setDot('err');
          txt.className = 'port-status-text';
          txt.textContent = 'Снаружи не достучались — проверь проброс и фаервол.';
          setPill(String(port), 'bad');
        }}
      }} catch(e) {{
        setDot('warn');
        txt.className = 'port-status-text';
        txt.textContent = 'Сеть или CORS — попробуй позже.';
        setPill('—', '');
      }} finally {{
        btn.disabled = false;
      }}
    }}
    btn.addEventListener('click', runProbe);
  }})();
  activate('script');
}})();
</script>
</body>
</html>"""


def diagnostics_page(version: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><title>diagnostics</title></head>
<body style="font-family:monospace;padding:1rem;background:#111;color:#eee"><pre>nodeadline master v{version}
</pre></body></html>"""
