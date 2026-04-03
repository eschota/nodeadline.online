let IS_OWNER=false;
let CAN_PORT=false;
let LOOPBACK=false;
let HOSTED_MASTER=false;
let OWNER_SUB='';
function canManageFolders(){
  return (LOOPBACK||IS_OWNER)&&!HOSTED_MASTER;
}
function canManageShareEntry(s){
  if(s.owner_sub){
    return IS_OWNER&&String(s.owner_sub)===String(OWNER_SUB||'');
  }
  return LOOPBACK||IS_OWNER;
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function toast(msg,kind,durationMs){
  const host=document.getElementById('toast-host');if(!host||!msg)return;
  const t=document.createElement('div');t.className='toast toast-'+(kind||'info');t.setAttribute('role','status');t.textContent=msg;
  host.appendChild(t);
  const ms=durationMs!=null&&durationMs>0?durationMs:4000;
  setTimeout(()=>{t.classList.add('toast-out');setTimeout(()=>t.remove(),280)},ms);
}
function parseFetchErrorBody(data, statusText){
  if(data&&typeof data==='object'&&data.error!=null)return String(data.error);
  if(typeof data==='string'){
    var t=data.trim();
    if(t.startsWith('<')||t.length>800)return '';
    return t;
  }
  return '';
}
function humanizeHttpFailure(status, statusText, detail){
  var d=(detail&&String(detail).trim())||'';
  var low=d.toLowerCase();
  var st=typeof status==='number'?status:parseInt(String(status||0),10)||0;
  if(d==='sync_failed'){
    return 'Синхронизация канала /site/ не выполнена (сеть, мастер или ошибка на диске).';
  }
  if(low.indexOf('bad gateway')>=0||st===502){
    return 'Прокси не получил ответ от ноды (502). Обычно нода на ПК не запущена, порт закрыт снаружи или на мастере устарел адрес WAN:порт. Откройте интерфейс по http://127.0.0.1:порт/site/ на этом компьютере или проверьте сеть и проброс.';
  }
  if(st===503||low.indexOf('service unavailable')>=0){
    return 'Сервис временно недоступен (503).';
  }
  if(st===504||low.indexOf('gateway time')>=0){
    return 'Таймаут ответа от ноды (504).';
  }
  if(st===521){
    return 'Прокси не видит работающую ноду (521).';
  }
  if(!st||st===0){
    return 'Нет соединения с нодой (сеть или процесс остановлен).';
  }
  if(d&&d.length<220)return d;
  var stt=(statusText&&String(statusText).trim())||'';
  if(stt)return stt+' (HTTP '+st+')';
  return 'Ошибка HTTP '+st;
}
async function fetchJson(url,opts){
  const o=Object.assign({credentials:'same-origin'},opts||{});
  const r=await fetch(url,o);
  let data=null;const ct=r.headers.get('content-type')||'';
  if(ct.includes('application/json')){try{data=await r.json();}catch(e){data=null;}}
  else{try{data=await r.text();}catch(e){data=null;}}
  if(!r.ok){
    const detail=parseFetchErrorBody(data,r.statusText||'');
    const err=humanizeHttpFailure(r.status,r.statusText||'',detail);
    const e=new Error(err);e.status=r.status;e.body=data;throw e;
  }
  if(data&&typeof data==='object'&&data.ok===false&&data.error){
    const raw=String(data.error);
    const msg=raw==='sync_failed'
      ? 'Синхронизация канала /site/ не выполнена (сеть, мастер или ошибка на диске).'
      : raw;
    const e=new Error(msg);
    e.status=r.status;
    e.body=data;
    throw e;
  }
  return data;
}
async function j(u,o){return fetchJson(u,o)}
function post(u){return fetchJson(u,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}
var SITE_BUNDLE_SHA_KEY='nodeadline_site_bundle_sha_v1';
async function pollSiteChannel(){
  var st;
  try{ st=await j('/api/site/status'); }catch(e){ return; }
  var sha=String(st.bundle_sha256||'').toLowerCase().trim();
  var prev=localStorage.getItem(SITE_BUNDLE_SHA_KEY);
  if(prev===null){
    localStorage.setItem(SITE_BUNDLE_SHA_KEY,sha);
    return;
  }
  if(!st.active){
    return;
  }
  if(!sha||sha===prev){
    return;
  }
  if(sha.length>=12){
    localStorage.setItem(SITE_BUNDLE_SHA_KEY,sha);
    toast('Канал /site/ обновлён','success');
    setTimeout(function(){ location.reload(); },500);
    return;
  }
  try{
    var m=await j('/api/site/master-channel');
    if(!m||!m.ok)return;
    var ms=(m.bundle_sha256||'').toLowerCase();
    var ls=(st.bundle_sha256||'').toLowerCase();
    if(ms && ls!==ms){
      var hintKey='nodeadline_hint_'+ms.slice(0,16);
      if(!sessionStorage.getItem(hintKey)){
        sessionStorage.setItem(hintKey,'1');
        toast('На сервере новая версия сайта, ждём синхронизацию…','info');
      }
    }
  }catch(e){}
}
async function showSuccessOverlay(){
  const overlay=document.getElementById('success-overlay');
  if(!overlay)return;
  overlay.hidden=false;
  await new Promise(function(r){setTimeout(r,1600);});
  overlay.hidden=true;
}
function applyDockAvatar(me){
  var img=document.getElementById('dock-avatar');
  var fb=document.getElementById('dock-avatar-fallback');
  if(!img||!fb)return;
  if(me&&me.picture){
    img.onload=function(){
      img.hidden=false;
      fb.hidden=true;
    };
    img.onerror=function(){
      img.hidden=true;
      fb.hidden=false;
    };
    img.src=me.picture;
    img.alt=me.name||me.username||me.email||'';
  }else{
    img.removeAttribute('src');
    img.hidden=true;
    fb.hidden=false;
  }
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
  if(d.public_base_url)return String(d.public_base_url);
  if(!d.wan_ip||!d.public_port)return null;
  return "http://"+String(d.wan_ip)+":"+String(d.public_port)+"/";
}
function renderNetInner(d){
  const t=netTier(d);
  const dot=t==="ok"?"ok":t==="warn"?"warn":"idle";
  let title="Только локально",sub="Пока нет доступа из интернета — только с этого ПК.";
  if(t==="ok"){title="В сети";sub="Роутер пробрасывает порт на этот компьютер.";}
  if(t==="warn"){title="С ограничениями";sub="UPnP мог создать проброс, но TCP с мастера до WAN:порт не доходит (другой внешний порт, файрвол провайдера, Full Cone NAT). Попробуй «Другой внешний порт» или укажи порт вручную.";}
  const listen=d.listen_port!=null&&d.listen_port!==''?String(d.listen_port):'—';
  const upnp=String(d.upnp_status||'—');
  const pe=d.wan_ip&&d.public_port?String(d.wan_ip)+':'+String(d.public_port):'—';
  const probe=String(d.public_probe_status||'—');
  let h='<div class="net-head"><span class="net-dot '+dot+'"></span><div>';
  h+='<p class="net-title">'+esc(title)+'</p><p class="net-sub">'+esc(sub)+'</p>';
  h+='<p class="net-metrics meta">локальный <b>'+esc(listen)+'</b> · UPnP <b>'+esc(upnp)+'</b> · WAN <b>'+esc(pe)+'</b> · проверка <b>'+esc(probe)+'</b></p>';
  if(d.upnp_last_error){
    h+='<p class="meta net-err-line">'+esc(String(d.upnp_last_error))+'</p>';
  }
  const u=publicUrl(d);
  if(u)h+='<p class="net-url">'+esc(u)+'</p>';
  h+='</div></div>';
  if(d.port_diag){
    try{
      const js=JSON.stringify(d.port_diag,null,2);
      h+='<details class="net-diag-dtl"><summary>Диагностика порта (последняя)</summary><pre class="net-diag-pre">'+esc(js)+'</pre></details>';
    }catch(e){}
  }
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
async function maybeRedirectPublic(d){
  if(sessionStorage.getItem("nodeadline_skip_pub_redirect"))return;
  if(sessionStorage.getItem("nodeadline_pub_redirect_done"))return;
  const h=location.hostname;
  if(h!=="127.0.0.1"&&h!=="localhost")return;
  const u=publicUrl(d);
  if(!u)return;
  const dnsOk=String(d.dns_status||"")==="ok";
  const reachable=String(d.public_probe_status||"")==="reachable";
  const isHttps=u.indexOf("https://")===0;
  if(!((isHttps&&dnsOk)||reachable))return;
  let base=u;
  if(!base.endsWith("/"))base+="/";
  sessionStorage.setItem("nodeadline_pub_redirect_done","1");
  try{
    const r=await fetch("/api/session/handoff",{credentials:"same-origin"});
    if(r.ok){
      const j=await r.json();
      if(j&&j.token){
        const claimUrl=new URL("api/session/claim",base);
        claimUrl.searchParams.set("token",j.token);
        location.href=claimUrl.toString();
        return;
      }
    }
  }catch(e){}
  location.href=base+"site/index.html?local=1";
}
function _domainStepIcon(done,active){
  if(done)return '<span style="color:var(--ok)">✓</span>';
  if(active)return '<span style="color:var(--accent)">…</span>';
  return '<span style="color:var(--muted)">○</span>';
}
async function loadDomain(){
  var el=document.getElementById('domain-panel-body');
  if(!el)return;
  try{
    var d=await j('/api/port/status');
    var stage=String(d.dns_pipeline_stage||'idle');
    var st=String(d.dns_status||'idle');
    var fq=d.dns_fqdn?String(d.dns_fqdn):'—';
    var email=d.oauth_email?String(d.oauth_email):'';
    if(!email){
      try{
        const me=await j('/api/me');
        if(me&&me.authenticated&&me.email)email=String(me.email);
      }catch(e){}
    }
    var wan=d.wan_ip?String(d.wan_ip):'';
    var sAuth=!!email;
    var sWan=!!wan;
    var sDns=st==='ok';
    var err=d.dns_error?('<p class="meta" style="color:var(--err);margin:.5rem 0 0">'+esc(String(d.dns_error))+'</p>'):'';
    var pub='';
    if(d.public_base_url){
      var u=String(d.public_base_url);
      pub='<p class="domain-url" style="margin:.5rem 0 0"><a href="'+esc(u)+'" rel="noopener">'+esc(u)+'</a></p>';
    }else{
      pub='<p class="meta" style="margin:.5rem 0 0">Полный URL появится после входа, WAN, DNS и внешнего порта (см. «Сеть»).</p>';
    }
    var lines='<ul class="domain-pipeline meta" style="margin:.35rem 0 0;padding-left:1.1rem;line-height:1.65">';
    lines+='<li>'+_domainStepIcon(sAuth,stage==='need_auth')+' Почта (Google): '+(email?('<b>'+esc(email)+'</b>'):'не выполнен вход')+'</li>';
    lines+='<li>'+_domainStepIcon(sWan&&(stage!=='need_wan'||wan),stage==='need_wan')+' Публичный IP (WAN): '+(wan?('<b>'+esc(wan)+'</b>'):'— настройте в «Сеть» / UPnP')+'</li>';
    var hasPub=d.public_port!=null&&d.public_port!=='';
    lines+='<li>'+_domainStepIcon(hasPub&&(stage!=='need_public_port'),stage==='need_public_port')+' Внешний порт: '+(hasPub?('<b>'+esc(String(d.public_port))+'</b>'):'— настройте UPnP или вручную в «Сеть»')+'</li>';
    lines+='<li>'+_domainStepIcon(sDns,stage==='dns_pending'||stage==='claiming')+' DNS: <b>'+esc(fq)+'</b> · '+esc(st)+(stage==='claiming'?' (обновление…)':'')+'</li>';
    lines+='<li>'+_domainStepIcon(!!d.public_base_url,false)+' Публичная ссылка</li></ul>';
    el.innerHTML=lines+pub+err;
  }catch(e){
    el.innerHTML='<p class="meta" style="color:var(--err)">'+(e.message||String(e))+'</p>';
  }
}
function renderUserDirectoryCard(u){
  var pic=String(u.picture||'').trim();
  var site=String(u.public_site_url||'').trim()||String(u.public_base_url||'').trim();
  var base=String(u.public_base_url||'').trim();
  var uname=String(u.username||'').trim();
  var email=String(u.email||'').trim();
  var name=String(u.name||'').trim();
  var fqdn=String(u.fqdn||'').trim();
  var wan=String(u.wan_ipv4||'').trim();
  var dnsAt=String(u.dns_updated_at||'').trim();
  var loginLabel=uname||'—';
  var loginHref=site||base||'';
  var nameLabel=name||'—';
  var nameHref=site||base||(email?('mailto:'+email):'');
  var fqdnHref=fqdn?('https://'+fqdn+'/'):'';
  var avatarHtml;
  if(/^https?:\/\//i.test(pic)){
    avatarHtml='<a class="user-card-avatar-link" href="'+esc(pic)+'" target="_blank" rel="noopener noreferrer"><img class="user-card-avatar" src="'+esc(pic)+'" alt="" width="56" height="56" decoding="async" referrerpolicy="no-referrer"/></a>';
  }else{
    var ini=(loginLabel!=='—'?loginLabel:'?').charAt(0).toUpperCase();
    avatarHtml='<span class="user-card-avatar-fallback" aria-hidden="true">'+esc(ini)+'</span>';
  }
  function extLink(href,label){
    href=String(href||'').trim();
    if(!href||href==='#')return '<span class="user-card-link user-card-na">'+esc(label)+'</span>';
    var isMail=href.indexOf('mailto:')===0;
    return '<a class="user-card-link" href="'+esc(href)+'"'+(isMail?'':' target="_blank" rel="noopener noreferrer"')+'>'+esc(label)+'</a>';
  }
  var html='<article class="user-card"><div class="user-card-head">'+avatarHtml+'<div class="user-card-main">';
  html+='<div class="user-card-line"><span class="user-card-k">Логин</span> '+extLink(loginHref,loginLabel)+'</div>';
  html+='<div class="user-card-line"><span class="user-card-k">Имя</span> '+extLink(nameHref,nameLabel)+'</div>';
  html+='<div class="user-card-line"><span class="user-card-k">Email</span> '+(email?extLink('mailto:'+email,email):'<span class="user-card-na">—</span>')+'</div>';
  html+='<div class="user-card-line"><span class="user-card-k">Домен</span> '+(fqdn?extLink(fqdnHref,fqdn):'<span class="user-card-na">—</span>')+'</div>';
  if(wan||dnsAt){
    html+='<div class="user-card-line user-card-line--meta"><span class="user-card-k">Сеть</span> <span class="user-card-meta">'+(wan?esc(wan):'—')+(dnsAt?' · '+esc(dnsAt):'')+'</span></div>';
  }
  html+='</div></div></article>';
  return html;
}
async function loadUsersDirectory(){
  var el=document.getElementById('users-directory-body');
  if(!el)return;
  el.innerHTML='<p class="meta">Загрузка…</p>';
  try{
    var d=await j('/api/directory/users');
    var users=(d&&d.users)||[];
    var err=d&&d.error;
    if(err&&(!users||!users.length)){
      el.innerHTML='<p class="meta" style="color:var(--red)">'+esc(String(err))+'</p>';
      return;
    }
    if(!users.length){
      el.innerHTML='<p class="meta">Пока нет записей на мастере.</p>';
      return;
    }
    var parts=[];
    for(var i=0;i<users.length;i++){
      parts.push(renderUserDirectoryCard(users[i]));
    }
    el.innerHTML='<div class="users-directory-grid">'+parts.join('')+'</div>';
  }catch(e){
    el.innerHTML='<p class="meta" style="color:var(--red)">'+(e.message||String(e))+'</p>';
  }
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
      await showSuccessOverlay();
      await maybeRedirectPublic(d);
    }else if(d){
      toast('Проверка: порт недоступен снаружи или не настроен','warn');
    }
  }catch(e){
    toast(e.message||'Ошибка проверки','err');
  }finally{
    if(btn){btn.disabled=false;btn.classList.remove('btn-loading');}
  }
}
async function upnpRemap(){
  if(!CAN_PORT)return;
  const btn=document.getElementById('btn-upnp-remap');
  if(btn){btn.disabled=true;btn.classList.add('btn-loading');}
  try{
    const r=await fetchJson('/api/port/upnp-remap',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d=r.state||await loadNet({skipRedirect:true});
    if(d)applyNetView(d);
    if(r.reachable){
      toast('Внешний порт '+String(r.external_port)+' — доступен с мастера','success');
      await maybeRedirectPublic(d);
    }else if(r.status==='mapped'){
      toast('Проброс '+String(r.external_port)+' создан, но снаружи не виден — см. диагностику','warn');
    }else{
      toast('Не удалось подобрать порт — см. диагностику','warn');
    }
  }catch(e){
    toast(e.message||'Ошибка UPnP','err');
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
      await showSuccessOverlay();
      if(st)await maybeRedirectPublic(st);
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
    try{const lp=d.listen_port!=null?d.listen_port:null;updateExtBanner(lp);updatePortRemoteMsg(lp);}catch(e){}
    try{loadDomain();}catch(e){}
    if(!skipRedirect){
      try{await maybeRedirectPublic(d);}catch(e){}
    }
    return d;
  }catch(e){
    el.innerHTML='<span style="color:var(--err)">'+(e.message?esc(e.message):'Сеть недоступна')+'</span>';
    updateNetPill({public_probe_status:'',public_port:null,wan_ip:null});
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
    if(lt.libtorrent==='unavailable'){
      lines.push('<div class="meta"><b>libtorrent</b>: <span style="color:var(--muted)">не установлен</span> — канал /site/ по HTTPS</div>');
    }else{
      lines.push('<div class="meta"><b>libtorrent</b>: '+(lt.session||'—')+(lt.dht_nodes!=null?' · DHT: '+lt.dht_nodes:'')+(lt.last_error?(' · <span style="color:var(--err)">'+esc(String(lt.last_error))+'</span>'):'')+'</div>');
    }
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
  }catch(e){el.innerHTML='<span style="color:var(--err)">'+(e.message?esc(e.message):esc(String(e)))+'</span>';}
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
function shareIndexLine(s){
  var st=String(s.scan_status||'');
  var ready=s.indexed_files!=null?Number(s.indexed_files):0;
  var total=s.files_total!=null?Number(s.files_total):ready;
  var b=fmtBytes(s.indexed_bytes!=null?Number(s.indexed_bytes):0);
  var pend=s.media_pending!=null?Number(s.media_pending):null;
  var pendPart='';
  if(pend!=null&&!isNaN(pend)&&pend>0){
    pendPart=' · <span class="meta">медиа без превью: '+esc(String(pend))+' (очередь обрабатывается)</span>';
  }
  if(st==='posters_pending'){
    return 'Индексация: ждём постеры/превью · готово '+esc(String(ready))+' / '+esc(String(total))+' файлов · '+b+pendPart;
  }
  if(st&&st!=='ready'){
    return 'Индексация: '+esc(st)+' · готово '+esc(String(ready))+' / '+esc(String(total))+' · '+b+pendPart;
  }
  return 'В индексе: '+esc(String(ready))+' / '+esc(String(total))+' файлов · '+b+pendPart;
}
async function loadShares(){
  const el=document.getElementById('shares');
  if(!el)return;
  if(HOSTED_MASTER){
    el.innerHTML='<span class=meta>Шары и индексация доступны только на процессе ноды. Установите ноду на ПК и откройте интерфейс по адресу ноды или localhost.</span>';
    return;
  }
  let list;
  try{list=await j('/api/shares');}catch(e){
    el.innerHTML='<span class=meta>Не удалось загрузить шары: '+esc(e.message||'')+'</span>';
    return;
  }
  if(!list.length){
    el.innerHTML=canManageFolders()
      ?'<span class=meta>Пока пусто — добавьте папку кнопкой выше или укажите полный путь к каталогу на машине, где запущена нода (нативный выбор папки — только с localhost).</span>'
      :'<span class=meta>Пока пусто. С этой страницы папки можно добавить после входа в аккаунт или с localhost.</span>';
    return;
  }
  el.innerHTML=list.map(function(s){
    var snap=(canManageShareEntry(s)&&s.owner_sub)?'<button class=btn onclick="pub(\''+s.share_id+'\')">Снимок</button>':'';
    var visSel='';
    if(canManageShareEntry(s)){
      visSel='<label class=meta style="display:inline-flex;align-items:center;gap:.35rem;margin-left:.35rem">видимость <select class=input style="width:auto;min-width:5rem" onchange="setShareVis(\''+s.share_id+'\',this.value)">'+
        '<option value="public"'+(s.visibility==='public'?' selected':'')+'>public</option>'+
        '<option value="private"'+(s.visibility==='private'?' selected':'')+'>private</option></select></label>';
    }else{
      visSel='<span class=meta style="margin-left:.35rem">'+esc(s.visibility)+'</span>';
    }
    var delBtn=canManageShareEntry(s)?'<button class=btn onclick="del(\''+s.share_id+'\')">Убрать</button>':'';
    return '<div class=item><div><b>'+esc(s.mount_path)+'</b><div class=meta>'+esc(s.local_path)+' · rev '+esc(String(s.snapshot_revision))+visSel+'</div>'+
    '<div class=meta style="margin-top:.25rem">'+shareIndexLine(s)+'</div></div>'+
    '<div class=row><button class=btn onclick="listFiles(\''+s.share_id+'\')">Файлы</button>'+snap+delBtn+'</div></div>';
  }).join('');
}
async function setShareVis(id,vis){
  try{
    await fetchJson('/api/shares/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({visibility:vis})});
    toast('Сохранено','success');
    loadShares();
  }catch(e){toast(e.message||'Ошибка','err');}
}
function addFolderPrimary(){
  if(LOOPBACK){
    pickFolder();
    return;
  }
  var det=document.getElementById('folders-manual');
  if(det){
    det.open=true;
  }
  var lp=document.getElementById('lp');
  if(lp){
    try{
      lp.scrollIntoView({behavior:'smooth',block:'nearest'});
    }catch(e){
      lp.scrollIntoView();
    }
    setTimeout(function(){lp.focus();},200);
  }
  var msg=!IS_OWNER
    ?'Сначала войдите через Google на этом поддомене — по HTTPS добавлять папку может только вошедший владелец. Затем раскройте форму ниже, укажите полный путь на ПК с нодой и нажмите «Добавить».'
    :'Укажите полный путь к каталогу на компьютере, где запущена нода, имя в URL и нажмите «Добавить». Системный диалог выбора папки с браузера недоступен — только путь вручную.';
  toast(msg,'info',10000);
}
async function pickFolder(){
  if(!LOOPBACK){
    toast('Выбор папки через системный диалог доступен только с локального интерфейса (127.0.0.1 / localhost). Укажите полный путь к папке на машине с нодой вручную.','err');
    return;
  }
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
  const lpEl=document.getElementById('lp');
  const mpEl=document.getElementById('mp');
  if(!lpEl||!mpEl)return;
  const lp=lpEl.value.trim();
  const mp=(mpEl.value.trim()||'share').replace(/^\/+|\/+$/g,'');
  if(!lp){
    toast('Укажи полный путь к папке','err');
    return;
  }
  if(!mp||mp.includes('..')||!/^[a-zA-Z0-9_\-/]+$/.test(mp)){
    toast('Недопустимое имя в URL (буквы, цифры, _, -, / без ..)','err');
    return;
  }
  var visEl=document.getElementById('share-vis');
  var vis=visEl&&visEl.value?visEl.value:'public';
  if(vis!=='public'&&vis!=='private')vis='public';
  try{
    await fetchJson('/api/shares',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({local_path:lp,mount_path:mp,visibility:vis})});
    toast('Шар добавлен','success');
    loadShares();
    loadPubs();
  }catch(e){
    var m=e.message||'Ошибка';
    var st=e.status||0;
    if(st===401||(typeof m==='string'&&(m.indexOf('not_authenticated')>=0||m.indexOf('401')>=0))){
      m='Нужна сессия: войдите через Google на этом же адресе (поддомен), затем снова нажмите «Добавить».';
    }else if(st===403||(typeof m==='string'&&m.indexOf('Forbidden')>=0)){
      m='Доступ запрещён (403). Войдите как владелец ноды.';
    }
    toast(m,'err',8000);
  }
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
  el.innerHTML=list.length?list.map(s=>`<div class=item><b>${esc(s.mount_path)}</b> <a class=btn href="/p/${s.public_slug}/">Открыть</a></div>`).join(''):'<span class=meta>Пока нет публичных папок. Добавь папку выше — она появится здесь для превью по ссылке.</span>';
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
let marketplacePage=1;
function marketplaceAddressLines(d){
  const parts=[];
  if(d&&d.site_origin)parts.push('Сейчас открыто: '+String(d.site_origin));
  if(d&&d.public_base_url)parts.push('Публичный адрес (DNS): '+String(d.public_base_url));
  return parts.length?parts.join(' · '):('Локально: '+location.origin+'/');
}
function applyMarketplaceStripVisibility(){
  const strip=document.getElementById('marketplace-strip');
  const btn=document.getElementById('marketplace-toggle');
  const exp=document.getElementById('marketplace-expanded');
  if(!strip)return;
  strip.hidden=HOSTED_MASTER;
  if(HOSTED_MASTER){
    if(exp)exp.hidden=true;
    if(btn){
      btn.setAttribute('aria-expanded','false');
      btn.classList.remove('is-open');
    }
  }
}
function initMarketplaceToggle(){
  const btn=document.getElementById('marketplace-toggle');
  const exp=document.getElementById('marketplace-expanded');
  if(!btn||!exp)return;
  btn.addEventListener('click',function(){
    if(HOSTED_MASTER)return;
    const willOpen=exp.hidden;
    if(willOpen){
      exp.hidden=false;
      btn.setAttribute('aria-expanded','true');
      btn.classList.add('is-open');
      loadMarketplace(1,false);
    }else{
      exp.hidden=true;
      btn.setAttribute('aria-expanded','false');
      btn.classList.remove('is-open');
    }
  });
}
async function loadMarketplace(page, quiet){
  const addr=document.getElementById('marketplace-address');
  const stats=document.getElementById('marketplace-stats');
  const grid=document.getElementById('marketplace-grid');
  const pager=document.getElementById('marketplace-pager');
  if(!grid)return;
  if(HOSTED_MASTER)return;
  if(typeof page==='number'&&page>=1)marketplacePage=page;
  const p=Math.max(1,parseInt(String(marketplacePage),10)||1);
  marketplacePage=p;
  if(!quiet)grid.innerHTML='<p class="meta">Загрузка…</p>';
  try{
    const d=await j('/api/marketplace?page='+p+'&per_page=100');
    if(addr)addr.textContent=marketplaceAddressLines(d);
    const total=d.total!=null?d.total:0;
    const per=d.per_page||100;
    const tp=Math.max(1,Math.ceil(total/per));
    if(stats){
      stats.textContent=total
        ?('В галерее: '+total+' · по дате индексации · стр. '+p+' / '+tp)
        :'Пусто: в галерею попадают только файлы с готовым превью (постер *_poster.jpg). Нужны ffmpeg и завершённые задачи индекса — см. «Папки» и «Трафик».';
    }
    const items=d.items||[];
    grid.innerHTML=items.length?items.map(function(it){
      const thumb=it.thumb_url||'';
      const view=it.view_url||'#';
      const cap=esc(it.mount_path||'')+' · '+esc(it.relative_path||'');
      const vd=it.media_type==='video'?'<span class="marketplace-video-badge">видео</span>':'';
      return '<div class="marketplace-item" role="listitem"><a href="'+esc(view)+'" target="_blank" rel="noopener">'+
        '<img class="marketplace-thumb" src="'+esc(thumb)+'" alt="" loading="lazy" width="160" height="120"/>'+
        '</a><p class="marketplace-cap">'+cap+'</p>'+vd+'</div>';
    }).join(''):'<p class="meta">На этой странице пусто.</p>';
    if(pager){
      const parts=[];
      if(p>1)parts.push('<button type="button" class="btn btn-sm" id="marketplace-prev">Назад</button>');
      if(p<tp)parts.push('<button type="button" class="btn btn-sm" id="marketplace-next">Вперёд</button>');
      pager.innerHTML=parts.join(' ');
      const prev=document.getElementById('marketplace-prev');
      const next=document.getElementById('marketplace-next');
      if(prev)prev.addEventListener('click',function(){loadMarketplace(p-1);});
      if(next)next.addEventListener('click',function(){loadMarketplace(p+1);});
    }
  }catch(e){
    if(addr)addr.textContent='';
    if(stats)stats.textContent=e.message||'Не удалось загрузить галерею';
    grid.innerHTML='<p class="meta">'+(e.message||'Ошибка')+'</p>';
    if(pager)pager.innerHTML='';
  }
}
async function copyDiag(){
  const d=await j('/api/diagnostics');
  document.getElementById('diag').textContent=JSON.stringify(d,null,2);
  navigator.clipboard.writeText(JSON.stringify(d,null,2));
}
function applyHostedMasterBanner(){
  if(document.body.classList.contains('ndl-hosted-master'))return;
  document.body.classList.add('ndl-hosted-master');
  var sub=document.querySelector('.subtitle');
  if(sub)sub.textContent='Статика мастера (нода на этом хосте не запущена)';
  var b=document.createElement('div');
  b.className='ndl-hosted-banner';
  b.setAttribute('role','status');
  b.innerHTML='<p><strong>Это страница на мастере.</strong> Здесь отдаётся тот же интерфейс, что у ноды, но без процесса ноды: сеть, шары и остальное заработают после установки ноды на ваш ПК и привязки домена.</p>';
  var w=document.querySelector('.wrap');
  if(w)w.insertBefore(b,w.firstChild);
  else document.body.insertBefore(b,document.body.firstChild);
}
async function loadVer(){
  const el=document.getElementById('overlay-version');
  if(!el)return;
  try{
    const d=await j('/api/version');
    if(d&&(d.role==='master'||d.hosted_static_site)){
      HOSTED_MASTER=true;
      applyHostedMasterBanner();
      var mv=d.master_version||'';
      var sr=d.site_revision;
      var sfx='';
      if(sr!=null&&sr!==''&&!isNaN(Number(sr))&&Number(sr)>0)sfx=' · /site/ rev '+String(sr);
      el.textContent=mv?('мастер '+mv+sfx):('мастер'+sfx);
      sessionStorage.setItem('nodeadline_verline',el.textContent);
      applyMarketplaceStripVisibility();
      return;
    }
    const parts=[];
    if(d.node_version)parts.push('узел v'+d.node_version);
    if(d.installer_build)parts.push('сборка '+d.installer_build);
    var srev=d.site_revision;
    var sn=srev!=null&&srev!==''?Number(srev):NaN;
    if(!isNaN(sn)&&(sn>0||d.site_active))parts.push('/site/ rev '+String(sn));
    const line=parts.join(' · ');
    const key='nodeadline_verline';
    sessionStorage.setItem(key,line);
    el.textContent=line;
    HOSTED_MASTER=false;
  }catch(e){}
  applyMarketplaceStripVisibility();
}
function applyFolderPanelVisibility(){
  const can=canManageFolders();
  const fm=document.getElementById('folders-manual');
  const fc=document.getElementById('folders-cta-row');
  if(fm)fm.hidden=!can;
  if(fc)fc.hidden=!can;
  var pick=document.getElementById('btn-add-folder-pick');
  var pickIn=document.getElementById('btn-pick-folder-inline');
  if(pick){
    pick.hidden=!can;
    if(can){
      pick.textContent=LOOPBACK?'Добавить папку':'Указать путь и добавить';
    }
  }
  if(pickIn)pickIn.hidden=!LOOPBACK||!can;
  var httpsHint=document.getElementById('folders-https-hint');
  if(httpsHint){
    if(can&&!HOSTED_MASTER&&!LOOPBACK){
      httpsHint.hidden=false;
      httpsHint.style.display='block';
      httpsHint.textContent='По этому адресу (не localhost): войдите через Google, нажмите «Указать путь и добавить», введите полный путь к папке на том же ПК, где запущена нода (например C:\\Users\\… или /home/…), имя в URL и «Добавить». Без входа запрос будет отклонён.';
    }else{
      httpsHint.hidden=true;
      httpsHint.style.display='none';
      httpsHint.textContent='';
    }
  }
  var intro=document.getElementById('folders-intro');
  if(intro){
    if(!intro.dataset.ndlDefaultIntro){
      intro.dataset.ndlDefaultIntro=intro.textContent;
    }
    if(HOSTED_MASTER){
      intro.textContent='На этом хосте отдаётся только статика мастера: шары и индексация работают на установленной ноде.';
    }else{
      intro.textContent=intro.dataset.ndlDefaultIntro||'';
    }
  }
}
function updateFoldersQueueHint(d){
  var hint=document.getElementById('folders-queue-hint');
  if(!hint)return;
  if(HOSTED_MASTER||!d||!d.ok){
    hint.hidden=true;
    hint.textContent='';
    return;
  }
  var qp=d.queue_pending||0;
  var qpr=d.queue_processing||0;
  var q=qp+qpr;
  var parts=['В очереди задач: '+q];
  var lf=d.last_failed;
  if(lf&&lf.error){
    parts.push('последняя ошибка: '+String(lf.error).slice(0,140));
  }
  hint.textContent=parts.join(' · ');
  hint.hidden=false;
}
function initPerfOverlay(){
  var el=document.getElementById('overlay-perf');
  if(!el)return;
  var t0=typeof window.__NDL_T0==='number'?window.__NDL_T0:performance.now();
  var nav=performance.getEntriesByType&&performance.getEntriesByType('navigation')[0];
  var loadMs=nav&&nav.loadEventEnd>0?Math.round(nav.loadEventEnd-nav.fetchStart):null;
  if(loadMs==null&&performance.timing&&performance.timing.loadEventEnd>0){
    var pt=performance.timing;
    loadMs=Math.round(pt.loadEventEnd-pt.fetchStart);
  }
  function paint(){
    requestAnimationFrame(function(){
      requestAnimationFrame(function(){
        var renderMs=Math.round(performance.now()-t0);
        var parts=[];
        if(loadMs!=null)parts.push('загрузка '+loadMs+' ms');
        parts.push('рендер '+renderMs+' ms');
        el.textContent=parts.join(' · ');
      });
    });
  }
  if(document.readyState==='complete')paint();
  else window.addEventListener('load',paint);
}
function updatePortRemoteMsg(listenPort){
  const el=document.getElementById('port-remote-msg');
  if(!el)return;
  if(CAN_PORT){el.hidden=true;return;}
  el.hidden=false;
  const lp=listenPort!=null&&listenPort!==''?String(listenPort):'';
  if(lp)el.innerHTML='<p class="meta" style="margin:.5rem 0 0;font-size:.72rem">Порт можно менять с этого компьютера (<a href="http://127.0.0.1:'+lp+'/site/index.html?local=1">127.0.0.1</a>) или после входа в аккаунт.</p>';
  else el.innerHTML='<p class="meta" style="margin:.5rem 0 0;font-size:.72rem">Порт можно менять с localhost или после входа.</p>';
}
function updateExtBanner(listenPort){
  const b=document.getElementById('ext-banner');
  if(!b)return;
  if(LOOPBACK){b.hidden=true;return;}
  b.hidden=false;
  const a=b.querySelector('a');
  if(a&&listenPort!=null&&listenPort!=='')a.href='http://127.0.0.1:'+String(listenPort)+'/?local=1';
}
function initTiles(){
  document.querySelectorAll('.tile[data-panel]').forEach(function(btn){
    btn.addEventListener('click',function(){
      stopStorageMonitor();
      var id=btn.getAttribute('data-panel');
      var panel=document.getElementById('panel-'+id);
      var was=btn.classList.contains('active');
      document.querySelectorAll('.tile[data-panel]').forEach(function(b){
        b.classList.remove('active');
        b.setAttribute('aria-expanded','false');
      });
      document.querySelectorAll('.expand-panel').forEach(function(p){p.hidden=true;});
      if(!was){
        btn.classList.add('active');
        btn.setAttribute('aria-expanded','true');
        if(panel){
          panel.hidden=false;
          if(id==='folders')loadShares();
          if(id==='domain')loadDomain();
          if(id==='users')loadUsersDirectory();
          if(id==='storage'){
            loadStorage();
            startStorageMonitor();
          }
        }
      }
    });
  });
}
function initDockDropdown(){
  var trigger=document.getElementById('dock-menu-trigger');
  var menu=document.getElementById('dock-dropdown');
  var lo=document.getElementById('dock-logout-btn');
  if(!trigger||!menu)return;
  function setOpen(open){
    menu.hidden=!open;
    trigger.setAttribute('aria-expanded',open?'true':'false');
  }
  setOpen(false);
  trigger.addEventListener('click',function(e){
    e.stopPropagation();
    setOpen(menu.hidden);
  });
  document.addEventListener('click',function(){
    setOpen(false);
  });
  menu.addEventListener('click',function(e){
    e.stopPropagation();
  });
  if(lo){
    lo.addEventListener('click',function(){
      fetch('/api/logout',{method:'POST',credentials:'same-origin'}).then(function(){location.reload();});
    });
  }
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'&&!menu.hidden)setOpen(false);
  });
}
function initTooltips(){
  var layer=document.getElementById('ndl-tip-layer');
  if(!layer){
    layer=document.createElement('div');
    layer.id='ndl-tip-layer';
    layer.className='ndl-tip-layer';
    layer.setAttribute('role','tooltip');
    layer.hidden=true;
    document.body.appendChild(layer);
  }
  function place(el){
    var r=el.getBoundingClientRect();
    var scrollX=window.scrollX||document.documentElement.scrollLeft;
    var scrollY=window.scrollY||document.documentElement.scrollTop;
    var top=r.bottom+8+scrollY;
    var w=layer.offsetWidth||200;
    var left=Math.min(Math.max(r.left+scrollX,8),scrollX+window.innerWidth-w-8);
    layer.style.top=top+'px';
    layer.style.left=left+'px';
  }
  function show(el){
    var t=el.getAttribute('data-tip');
    if(!t)return;
    layer.textContent=t;
    layer.hidden=false;
    requestAnimationFrame(function(){
      place(el);
    });
  }
  function hide(){
    layer.hidden=true;
  }
  document.querySelectorAll('.ndl-tip[data-tip]').forEach(function(el){
    el.addEventListener('mouseenter',function(){show(el);});
    el.addEventListener('mouseleave',hide);
    el.addEventListener('focusin',function(){show(el);});
    el.addEventListener('focusout',hide);
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'&&!layer.hidden)hide();
  });
}
function decimalTb(n){
  if(n==null||!isFinite(n)||n<0)return '—';
  return (n/1e12).toFixed(2)+' ТБ';
}

var STORAGE_SAMPLES_MAX=60;
var storageSamples=[];
var storagePollTimer=null;

function stopStorageMonitor(){
  if(storagePollTimer){clearInterval(storagePollTimer);storagePollTimer=null;}
}

function startStorageMonitor(){
  stopStorageMonitor();
  storagePollTimer=setInterval(function(){
    fetchDisksJson().then(function(d){
      applyStorageSnapshot(d);
    }).catch(function(){});
  },4000);
}

function formatBytes(n){
  if(n==null||!isFinite(n)||n<0)return '—';
  var u=['Б','КиБ','МиБ','ГиБ','ТиБ'];
  var i=0;
  var x=Number(n);
  while(x>=1024&&i<u.length-1){x/=1024;i++;}
  return (i===0?String(Math.round(x)):x.toFixed(1))+' '+u[i];
}

var STORAGE_RING_LEN=188.5;
function setStorageArc(el,pct){
  if(!el)return;
  var p=Math.max(0,Math.min(100,Number(pct)||0));
  el.setAttribute('stroke-dashoffset',String(STORAGE_RING_LEN*(1-p/100)));
  el.classList.remove('storage-kpi-arc--ok','storage-kpi-arc--warn','storage-kpi-arc--crit');
  if(p>=85)el.classList.add('storage-kpi-arc--crit');
  else if(p>=70)el.classList.add('storage-kpi-arc--warn');
  else el.classList.add('storage-kpi-arc--ok');
}
function storageVolFillClass(pct){
  var p=Number(pct)||0;
  if(p>=85)return 'storage-vol-tile--crit';
  if(p>=70)return 'storage-vol-tile--warn';
  return '';
}
function diskMaxPct(vols){
  var m=0;
  (vols||[]).forEach(function(v){
    var p=typeof v.percent==='number'?v.percent:0;
    if(p>m)m=p;
  });
  return m;
}
function setStorageTab(tab){
  var ok={disks:1,memory:1,cpu:1};
  if(!ok[tab])tab='disks';
  ['disks','memory','cpu'].forEach(function(t){
    var pan=document.getElementById('storage-tab-'+t);
    var head=document.getElementById('storage-tabhead-'+t);
    var k1=document.getElementById('storage-kpi-btn-'+t);
    var show=t===tab;
    if(pan)pan.hidden=!show;
    if(head){
      head.classList.toggle('is-active',show);
      head.setAttribute('aria-selected',show?'true':'false');
    }
    if(k1){
      k1.classList.toggle('is-active',show);
      k1.setAttribute('aria-pressed',show?'true':'false');
    }
  });
  if(tab==='memory')drawStorageChart();
  if(tab==='cpu')drawCpuChart();
}
function initStorageUi(){
  document.querySelectorAll('[data-storage-tab]').forEach(function(el){
    el.addEventListener('click',function(){
      var t=el.getAttribute('data-storage-tab');
      if(t)setStorageTab(t);
    });
  });
}
function redrawActiveStorageCharts(){
  var m=document.getElementById('storage-tab-memory');
  var c=document.getElementById('storage-tab-cpu');
  if(m&&!m.hidden)drawStorageChart();
  if(c&&!c.hidden)drawCpuChart();
}

function drawStorageChart(){
  var canvas=document.getElementById('storage-mem-chart');
  if(!canvas||!canvas.getContext)return;
  var ctx=canvas.getContext('2d');
  var dpr=window.devicePixelRatio||1;
  var rect=canvas.getBoundingClientRect();
  var W=Math.max(280,Math.floor(rect.width)||600);
  var H=192;
  canvas.width=Math.floor(W*dpr);
  canvas.height=Math.floor(H*dpr);
  ctx.setTransform(1,0,0,1,0,0);
  ctx.scale(dpr,dpr);
  var muted='rgba(100,100,115,0.45)';
  var grid='rgba(15,23,42,0.08)';
  var padL=40,padR=12,padT=14,padB=28;
  var plotW=W-padL-padR,plotH=H-padT-padB;
  var bgGrad=ctx.createLinearGradient(0,0,0,H);
  bgGrad.addColorStop(0,'rgba(248,250,252,0.95)');
  bgGrad.addColorStop(1,'rgba(241,245,249,0.9)');
  ctx.fillStyle=bgGrad;
  ctx.fillRect(0,0,W,H);
  ctx.strokeStyle='rgba(148,163,184,0.35)';
  ctx.lineWidth=1;
  ctx.strokeRect(0.5,0.5,W-1,H-1);
  [0,0.25,0.5,0.75,1].forEach(function(f){
    ctx.strokeStyle=grid;
    ctx.beginPath();
    var y=padT+plotH*(1-f);
    ctx.moveTo(padL,y);
    ctx.lineTo(padL+plotW,y);
    ctx.stroke();
    ctx.fillStyle=muted;
    ctx.font='600 10px ui-sans-serif,system-ui,sans-serif';
    ctx.textAlign='right';
    ctx.fillText(String(Math.round(f*100))+'%',padL-6,y+3);
  });
  ctx.textAlign='left';
  if(storageSamples.length===0){
    ctx.fillStyle=muted;
    ctx.font='12px ui-sans-serif,system-ui,sans-serif';
    ctx.fillText('Подождите — собираем выборку…',padL+8,padT+plotH/2);
    return;
  }
  function xAt(i,n){
    return padL+(n<=1?plotW/2:((i/(n-1))*plotW));
  }
  function yPct(p){
    return padT+plotH*(1-Math.min(100,Math.max(0,p))/100);
  }
  var n=storageSamples.length;
  var y0=padT+plotH;
  function fillUnder(getY,fillStyle){
    ctx.beginPath();
    ctx.moveTo(xAt(0,n),y0);
    storageSamples.forEach(function(p,i){
      ctx.lineTo(xAt(i,n),getY(p,i));
    });
    ctx.lineTo(xAt(n-1,n),y0);
    ctx.closePath();
    ctx.fillStyle=fillStyle;
    ctx.fill();
  }
  fillUnder(function(p){return yPct(p.swap);},'rgba(249,115,22,0.12)');
  fillUnder(function(p){return yPct(p.ram);},'rgba(34,197,94,0.14)');
  ctx.lineJoin='round';
  ctx.lineCap='round';
  ctx.lineWidth=2.25;
  ctx.strokeStyle='#ea580c';
  ctx.beginPath();
  storageSamples.forEach(function(p,i){
    var x=xAt(i,n),y=yPct(p.swap);
    if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
  });
  ctx.stroke();
  ctx.strokeStyle='#16a34a';
  ctx.beginPath();
  storageSamples.forEach(function(p,i){
    var x=xAt(i,n),y=yPct(p.ram);
    if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
  });
  ctx.stroke();
  if(n===1){
    ctx.fillStyle='#16a34a';
    ctx.beginPath();
    ctx.arc(xAt(0,n),yPct(storageSamples[0].ram),4,0,Math.PI*2);
    ctx.fill();
    ctx.strokeStyle='#fff';
    ctx.lineWidth=1;
    ctx.stroke();
    ctx.fillStyle='#ea580c';
    ctx.beginPath();
    ctx.arc(xAt(0,n),yPct(storageSamples[0].swap),4,0,Math.PI*2);
    ctx.fill();
    ctx.strokeStyle='#fff';
    ctx.stroke();
  }
}

function drawCpuChart(){
  var canvas=document.getElementById('storage-cpu-chart');
  if(!canvas||!canvas.getContext)return;
  var ctx=canvas.getContext('2d');
  var dpr=window.devicePixelRatio||1;
  var rect=canvas.getBoundingClientRect();
  var W=Math.max(280,Math.floor(rect.width)||600);
  var H=192;
  canvas.width=Math.floor(W*dpr);
  canvas.height=Math.floor(H*dpr);
  ctx.setTransform(1,0,0,1,0,0);
  ctx.scale(dpr,dpr);
  var muted='rgba(100,100,115,0.45)';
  var grid='rgba(15,23,42,0.08)';
  var padL=40,padR=12,padT=14,padB=28;
  var plotW=W-padL-padR,plotH=H-padT-padB;
  var bgGrad=ctx.createLinearGradient(0,0,0,H);
  bgGrad.addColorStop(0,'rgba(248,250,252,0.95)');
  bgGrad.addColorStop(1,'rgba(239,246,255,0.92)');
  ctx.fillStyle=bgGrad;
  ctx.fillRect(0,0,W,H);
  ctx.strokeStyle='rgba(148,163,184,0.35)';
  ctx.lineWidth=1;
  ctx.strokeRect(0.5,0.5,W-1,H-1);
  [0,0.25,0.5,0.75,1].forEach(function(f){
    ctx.strokeStyle=grid;
    ctx.beginPath();
    var y=padT+plotH*(1-f);
    ctx.moveTo(padL,y);
    ctx.lineTo(padL+plotW,y);
    ctx.stroke();
    ctx.fillStyle=muted;
    ctx.font='600 10px ui-sans-serif,system-ui,sans-serif';
    ctx.textAlign='right';
    ctx.fillText(String(Math.round(f*100))+'%',padL-6,y+3);
  });
  ctx.textAlign='left';
  if(storageSamples.length===0){
    ctx.fillStyle=muted;
    ctx.font='12px ui-sans-serif,system-ui,sans-serif';
    ctx.fillText('Подождите — собираем выборку…',padL+8,padT+plotH/2);
    return;
  }
  function xAt(i,n){
    return padL+(n<=1?plotW/2:((i/(n-1))*plotW));
  }
  function yPct(p){
    return padT+plotH*(1-Math.min(100,Math.max(0,p))/100);
  }
  var n=storageSamples.length;
  var y0=padT+plotH;
  var cpuGrad=ctx.createLinearGradient(0,padT,0,y0);
  cpuGrad.addColorStop(0,'rgba(59,130,246,0.35)');
  cpuGrad.addColorStop(1,'rgba(59,130,246,0.02)');
  ctx.beginPath();
  ctx.moveTo(xAt(0,n),y0);
  storageSamples.forEach(function(s,i){
    var c=typeof s.cpu==='number'?s.cpu:0;
    ctx.lineTo(xAt(i,n),yPct(c));
  });
  ctx.lineTo(xAt(n-1,n),y0);
  ctx.closePath();
  ctx.fillStyle=cpuGrad;
  ctx.fill();
  ctx.lineJoin='round';
  ctx.lineCap='round';
  ctx.lineWidth=2.5;
  ctx.strokeStyle='#2563eb';
  ctx.beginPath();
  storageSamples.forEach(function(s,i){
    var c=typeof s.cpu==='number'?s.cpu:0;
    var x=xAt(i,n),y=yPct(c);
    if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
  });
  ctx.stroke();
  if(n===1){
    var c0=typeof storageSamples[0].cpu==='number'?storageSamples[0].cpu:0;
    ctx.fillStyle='#2563eb';
    ctx.beginPath();
    ctx.arc(xAt(0,n),yPct(c0),4.5,0,Math.PI*2);
    ctx.fill();
    ctx.strokeStyle='#fff';
    ctx.lineWidth=1;
    ctx.stroke();
  }
}

function applyStorageSnapshot(d){
  d=d||{};
  var mem=d.memory;
  var sw=d.swap;
  var rss=d.node_rss_bytes;
  var err=d.memory_error;
  var cpu=d.cpu;
  var vols=d.volumes||[];
  var maxD=diskMaxPct(vols);
  var diskPctEl=document.getElementById('storage-kpi-disk-pct');
  var diskRing=document.getElementById('storage-kpi-disk-ring');
  if(diskPctEl&&diskRing){
    if(vols.length){
      diskPctEl.textContent=Math.round(maxD)+'%';
      setStorageArc(diskRing,maxD);
    }else{
      diskPctEl.textContent='—';
      setStorageArc(diskRing,0);
    }
  }
  var ramPctEl=document.getElementById('storage-kpi-ram-pct');
  var ramRing=document.getElementById('storage-kpi-ram-ring');
  if(ramPctEl&&ramRing){
    if(mem&&typeof mem.percent==='number'&&!err){
      ramPctEl.textContent=Math.round(mem.percent)+'%';
      setStorageArc(ramRing,mem.percent);
    }else{
      ramPctEl.textContent=err?'!':'—';
      setStorageArc(ramRing,0);
    }
  }
  var cpuPctEl=document.getElementById('storage-kpi-cpu-pct');
  var cpuRing=document.getElementById('storage-kpi-cpu-ring');
  if(cpuPctEl&&cpuRing){
    if(cpu&&typeof cpu.percent==='number'){
      cpuPctEl.textContent=Math.round(cpu.percent)+'%';
      setStorageArc(cpuRing,cpu.percent);
    }else{
      cpuPctEl.textContent='—';
      setStorageArc(cpuRing,0);
    }
  }
  var memEl=document.getElementById('storage-memory-compact');
  if(memEl){
    if(err){
      memEl.innerHTML='<div class="row"><span class="kv" style="color:var(--err)">'+esc(String(err))+'</span></div>';
    }else if(mem){
      var row='<div class="row">'+
        '<span class="kv">RAM <b>'+mem.percent+'%</b></span>'+
        '<span class="kv">своб. <b>'+formatBytes(mem.available)+'</b></span>';
      if(rss!=null)row+='<span class="kv">нода <b>'+formatBytes(rss)+'</b></span>';
      if(sw&&sw.total>0)row+='<span class="kv">swap <b>'+sw.percent+'%</b></span>';
      row+='</div>';
      memEl.innerHTML=row;
    }else{
      memEl.innerHTML='';
    }
  }
  var cpuCompact=document.getElementById('storage-cpu-compact');
  if(cpuCompact){
    if(cpu){
      var line='<div class="row"><span class="kv">загрузка <b>'+cpu.percent+'%</b></span>';
      if(cpu.cores_logical)line+='<span class="kv">ядер <b>'+cpu.cores_logical+'</b></span>';
      if(cpu.loadavg&&cpu.loadavg.length)line+='<span class="kv">load <b>'+cpu.loadavg.join(' · ')+'</b></span>';
      line+='</div>';
      cpuCompact.innerHTML=line;
    }else{
      cpuCompact.innerHTML='';
    }
  }
  var swapNote=document.getElementById('storage-swap-note');
  if(swapNote){
    if(sw&&sw.total===0){
      swapNote.hidden=false;
      swapNote.textContent='Своп 0 Б — линия swap на графике у оси 0%.';
    }else{
      swapNote.hidden=true;
      swapNote.textContent='';
    }
  }
  var wrap=document.getElementById('storage-chart-wrap');
  if(wrap){
    if(mem&&typeof mem.percent==='number'&&mem.percent>85)wrap.classList.add('storage-chart-wrap--warn');
    else wrap.classList.remove('storage-chart-wrap--warn');
  }
  var cpuWrap=document.querySelector('#storage-tab-cpu .storage-chart-wrap');
  if(cpuWrap){
    if(cpu&&typeof cpu.percent==='number'&&cpu.percent>85)cpuWrap.classList.add('storage-chart-wrap--warn');
    else cpuWrap.classList.remove('storage-chart-wrap--warn');
  }
  var ramPct=mem&&typeof mem.percent==='number'?mem.percent:0;
  var swapPct=(sw&&sw.total>0&&typeof sw.percent==='number')?sw.percent:0;
  var cpuPct=cpu&&typeof cpu.percent==='number'?cpu.percent:0;
  storageSamples.push({ram:ramPct,swap:swapPct,cpu:cpuPct});
  if(storageSamples.length>STORAGE_SAMPLES_MAX)storageSamples.shift();
  redrawActiveStorageCharts();
}

async function fetchDisksJson(){
  try{
    return await j('/api/system/disks');
  }catch(e){
    if(e.status===404){
      return await j('/api/diagnostics/disks');
    }
    throw e;
  }
}
async function diskApiErrorHtml(e){
  var msg=e.message||String(e);
  var st=e.status;
  var origin=location.origin;
  var logUrl=origin+'/api/node/log-view';
  var viewerUrl=origin+'/site/node-log.html';
  if(st===403||msg==='disk_api_forbidden'||(e.body&&e.body.error==='disk_api_forbidden')){
    msg='Нет доступа к API хранилища (диски, RAM) с этого адреса. Войдите в аккаунт или откройте ноду с localhost или из локальной сети.';
  }else if(st===404||msg==='Not Found'){
    msg='Сервер не отвечает этим API (404). Нужна актуальная сборка. Установщик после payload перезапускает ноду; при ручной подмене файлов процесс обновится сам (~30 с по маркеру в runtime) или перезапустите вручную.';
  }
  var extra='';
  try{
    var ps=await j('/api/port/status');
    var wan=ps.wan_ip,pub=ps.public_port;
    if(wan&&pub){
      extra='<p class="meta">С другой сети (WAN): <a href="'+esc('http://'+wan+':'+pub+'/api/node/log-view')+'" target="_blank" rel="noopener">http://'+esc(wan)+':'+esc(String(pub))+'/api/node/log-view</a></p>';
    }
  }catch(err){}
  return '<p class="meta" style="color:var(--err)">'+esc(msg)+'</p>'+
    '<p class="meta"><a href="'+esc(logUrl)+'" target="_blank" rel="noopener">Лог (страница с авто-подбором эндпоинта)</a> · '+
    '<a href="'+esc(viewerUrl)+'">Статическая страница лога</a></p>'+extra;
}
var DISK_VOL_ICO='<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z"/></svg>';
async function loadStorage(){
  var listEl=document.getElementById('storage-volumes-list');
  var hint=document.getElementById('storage-hint');
  var bench=document.getElementById('disk-bench-wrap');
  if(!listEl)return;
  if(hint){
    hint.textContent='ТБ — десятичные (10¹²). Опрос ~4 с, пока панель открыта.';
  }
  if(bench)bench.hidden=false;
  storageSamples=[];
  setStorageTab('disks');
  try{
    var d=await fetchDisksJson();
    applyStorageSnapshot(d);
    var vols=d.volumes||[];
    var sel=document.getElementById('disk-bench-mount');
    if(sel){
      sel.innerHTML='';
      vols.forEach(function(v){
        var o=document.createElement('option');
        o.value=v.mountpoint;
        o.textContent=v.mountpoint+(v.fstype?' ('+v.fstype+')':'');
        sel.appendChild(o);
      });
    }
    if(!vols.length){
      listEl.innerHTML='<p class="meta">Тома не найдены. Обновите ноду; на Windows список через диски и disk_usage.</p>';
      return;
    }
    listEl.innerHTML=vols.map(function(v){
      var pct=typeof v.percent==='number'?v.percent:0;
      var w=Math.min(100,Math.max(0,pct));
      var cls='storage-vol-tile';
      var vf=storageVolFillClass(pct);
      if(vf)cls+=' '+vf;
      var meta='<span>'+esc(decimalTb(v.total))+'</span><span>своб. '+esc(decimalTb(v.free))+'</span>';
      if(v.device)meta+='<span>'+esc(String(v.device))+'</span>';
      if(v.fstype)meta+='<span>'+esc(String(v.fstype))+'</span>';
      return '<div class="'+cls+'">'+
        '<div class="storage-vol-head">'+
        '<span class="storage-vol-ico">'+DISK_VOL_ICO+'</span>'+
        '<span class="storage-vol-pct">'+esc(String(Math.round(pct)))+'%</span></div>'+
        '<div class="storage-vol-path">'+esc(v.mountpoint)+'</div>'+
        '<div class="storage-vol-bar"><span style="width:'+w+'%"></span></div>'+
        '<div class="storage-vol-meta">'+meta+'</div></div>';
    }).join('');
  }catch(e){
    listEl.innerHTML=await diskApiErrorHtml(e);
    applyStorageSnapshot({});
  }
}
async function postDiskBenchmark(body){
  try{
    return await fetchJson('/api/system/disks/benchmark',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body),
    });
  }catch(e){
    if(e.status===404){
      return await fetchJson('/api/diagnostics/disks/benchmark',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body),
      });
    }
    throw e;
  }
}
function initDiskBench(){
  var btn=document.getElementById('disk-bench-btn');
  var sel=document.getElementById('disk-bench-mount');
  var out=document.getElementById('disk-bench-result');
  if(!btn||!sel||!out)return;
  btn.addEventListener('click',async function(){
    btn.disabled=true;
    out.textContent='Измерение…';
    try{
      var r=await postDiskBenchmark({mount_path:sel.value,size_mb:16});
      if(r&&r.error){
        out.innerHTML='<span style="color:var(--err)">'+esc(r.detail||r.error)+'</span>';
        return;
      }
      var line='Чтение: <b>'+esc(String(r.read_mbps))+'</b> МБ/с · Запись: <b>'+esc(String(r.write_mbps))+'</b> МБ/с';
      if(r.bench_note_ru)line+='<br><span class="meta">'+esc(r.bench_note_ru)+'</span>';
      out.innerHTML=line;
    }catch(e){
      out.textContent=e.message||String(e);
    }finally{
      btn.disabled=false;
    }
  });
}
function describeSiteSyncReason(applied,reason){
  if(applied)return 'Канал /site/ обновлён.';
  var m={
    up_to_date:'Канал /site/ уже актуален.',
    fetch_failed:'Не удалось получить site_channel с мастера.',
    invalid_channel:'Данные канала отклонены.',
    no_bundle_url:'Нет URL бандла для скачивания.',
    apply_failed:'Бандл не применился (SHA или архив).'
  };
  return m[reason]||String(reason||'');
}
var APPLY_UPGRADE_REPORT_KEY='nodeadline_apply_upgrade_report_v1';
function mapApplyUpgradeError(errCode){
  var m={
    sync_failed:'Синхронизация канала /site/ не выполнена (сеть, мастер или ошибка на диске).',
    disk_api_forbidden:'Нет доступа к этому действию.'
  };
  return m[errCode]||String(errCode||'ошибка');
}
function buildApplyUpgradeSummaryToast(r){
  var sync=describeSiteSyncReason(r.site_sync_applied,r.site_sync_reason);
  var pids=r.terminated_pids||[];
  var n=pids.length;
  var extra=n?(' Лишних процессов завершено: '+n+'.'):' Других процессов ноды не было.';
  return sync+extra+' Перезапуск ноды…';
}
function buildApplyUpgradeHtml(r,opts){
  opts=opts||{};
  var after=!!opts.afterReload;
  var title=after?'Последняя операция (после перезапуска ноды)':'Результат';
  var sync=describeSiteSyncReason(r.site_sync_applied,r.site_sync_reason);
  var pids=r.terminated_pids||[];
  var cleanupLine=pids.length
    ? ('Завершены другие процессы этой установки (PID: '+pids.join(', ')+').')
    : 'Других процессов этой установки не найдено.';
  var restartLine=after
    ? 'Перезапуск веб-сервера выполнен — вы уже на новой сессии ноды.'
    : 'Перезапуск веб-сервера запланирован; страница обновится автоматически через несколько секунд.';
  var i3=after?'✓':'…';
  return '<p class="system-apply-result-title">'+esc(title)+'</p>'+
    '<ol class="system-apply-steps">'+
    '<li><span class="system-apply-step-ic" aria-hidden="true">✓</span> <strong>Синхронизация /site/</strong> — '+esc(sync)+'</li>'+
    '<li><span class="system-apply-step-ic" aria-hidden="true">✓</span> <strong>Очистка процессов</strong> — '+esc(cleanupLine)+'</li>'+
    '<li><span class="system-apply-step-ic" aria-hidden="true">'+esc(i3)+'</span> <strong>Перезапуск ноды</strong> — '+esc(restartLine)+'</li>'+
    '</ol>';
}
function setApplyUpgradeResult(html,variant){
  var el=document.getElementById('system-apply-result');
  if(!el)return;
  el.hidden=false;
  el.className='system-apply-result system-apply-result--'+(variant||'ok');
  el.innerHTML=html;
}
function clearApplyUpgradeResult(){
  var el=document.getElementById('system-apply-result');
  if(!el)return;
  el.hidden=true;
  el.innerHTML='';
  el.className='system-apply-result';
}
function showApplyUpgradePending(){
  setApplyUpgradeResult(
    '<p class="system-apply-result-title">Выполняется…</p>'+
    '<ul class="system-apply-pending">'+
    '<li>запрос к мастеру и проверка канала <code>/site/</code>;</li>'+
    '<li>завершение лишних процессов этой установки;</li>'+
    '<li>планирование перезапуска веб-сервера.</li>'+
    '</ul>'+
    '<p class="meta system-apply-wait">Подождите ответ сервера…</p>',
    'pending'
  );
}
function restoreApplyUpgradeReportFromStorage(){
  var el=document.getElementById('system-apply-result');
  if(!el)return;
  try{
    var raw=sessionStorage.getItem(APPLY_UPGRADE_REPORT_KEY);
    if(!raw)return;
    sessionStorage.removeItem(APPLY_UPGRADE_REPORT_KEY);
    var o=JSON.parse(raw);
    if(!o||!o.ok||!o.r)return;
    setApplyUpgradeResult(buildApplyUpgradeHtml(o.r,{afterReload:true}),'ok');
  }catch(e){
    sessionStorage.removeItem(APPLY_UPGRADE_REPORT_KEY);
  }
}
async function postSystemApplyUpgrade(){
  return fetchJson('/api/system/apply-upgrade',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:'{}'
  });
}
function initSystemUpgrade(){
  var btn=document.getElementById('system-apply-btn');
  if(!btn)return;
  btn.addEventListener('click',async function(){
    if(!confirm('Проверить обновления и перезапустить ноду? Будет синхронизация канала /site/, завершение лишних процессов этой установки и перезапуск веб-сервера.'))return;
    btn.disabled=true;
    btn.classList.add('btn-loading');
    btn.setAttribute('aria-busy','true');
    clearApplyUpgradeResult();
    showApplyUpgradePending();
    var doneOk=false;
    try{
      var r=await postSystemApplyUpgrade();
      doneOk=true;
      setApplyUpgradeResult(buildApplyUpgradeHtml(r,{afterReload:false}),'ok');
      toast(buildApplyUpgradeSummaryToast(r),'success',5500);
      try{
        sessionStorage.setItem(APPLY_UPGRADE_REPORT_KEY,JSON.stringify({ok:true,r:r,ts:Date.now()}));
      }catch(e){}
      setTimeout(function(){ location.reload(); },4200);
    }catch(e){
      var st=e.status;
      var code=(e.body&&typeof e.body==='object'&&e.body.error!=null)?String(e.body.error):'';
      var human=e.message||String(e);
      if(st===403||(e.body&&e.body.error==='disk_api_forbidden')){
        human='Нет доступа: откройте с localhost, из LAN или войдите в аккаунт.';
      }else if(code&&code!=='sync_failed'){
        var mapped=mapApplyUpgradeError(code);
        if(mapped&&mapped!==code)human=mapped;
      }
      var httpMeta=st?('<p class="meta">HTTP <code>'+esc(String(st))+'</code>'+(code&&code!==human?(' · '+esc(code)):'')+'</p>'):'';
      setApplyUpgradeResult(
        '<p class="system-apply-result-title">Ошибка</p>'+
        '<p class="system-apply-err-body">'+esc(human)+'</p>'+httpMeta,
        'err'
      );
      toast(human,'err',6000);
    }finally{
      btn.classList.remove('btn-loading');
      btn.removeAttribute('aria-busy');
      if(!doneOk){btn.disabled=false;}
    }
  });
}
/** Индикатор в шапке: опрос локального веб-сервера ноды (GET /api/version). */
var NDL_HEALTH_POLL_MS = 4000;
var NDL_HEALTH_HTTP_MS = 6500;
var NDL_HEALTH_DEAD_FAILS = 5;
/** Подряд успешных проверок до того, как считать «нода стабильно работала» (для алерта при падении). */
var NDL_MIN_OK_STREAK_FOR_DOWN_ALERT = 5;

function initDockHealth() {
  var btn = document.getElementById("dock-health-btn");
  var tip = document.getElementById("dock-health-tooltip");
  var body = document.getElementById("dock-health-tooltip-body");
  var downBanner = document.getElementById("ndl-node-down-alert");
  var downDismiss = document.getElementById("ndl-node-down-alert-dismiss");
  if (!btn || !tip || !body) return;
  var failStreak = 0;
  var stableOkStreak = 0;
  var allowDisconnectBanner = false;
  var bannerDismissed = false;
  function showDownBanner() {
    if (HOSTED_MASTER || !downBanner) return;
    downBanner.hidden = false;
    downBanner.setAttribute("aria-hidden", "false");
    document.body.classList.add("ndl-node-down-visible");
  }
  function hideDownBanner() {
    if (!downBanner) return;
    downBanner.hidden = true;
    downBanner.setAttribute("aria-hidden", "true");
    document.body.classList.remove("ndl-node-down-visible");
  }
  if (downDismiss) {
    downDismiss.addEventListener("click", function () {
      hideDownBanner();
      bannerDismissed = true;
      allowDisconnectBanner = false;
      stableOkStreak = 0;
    });
  }
  function setTier(tier) {
    btn.classList.remove("dock-health--idle", "dock-health--ok", "dock-health--warn", "dock-health--dead");
    btn.classList.add("dock-health--" + tier);
    var title;
    var txt;
    if (tier === "idle") {
      title = "Проверка ноды…";
      txt = "Первая проверка соединения с локальным веб-сервером (GET /api/version).";
    } else if (tier === "ok") {
      title = "Нода на связи";
      txt =
        "Локальный веб-сервер отвечает. Опрос каждые " +
        String(Math.round(NDL_HEALTH_POLL_MS / 1000)) +
        " с.";
    } else if (tier === "warn") {
      title = "Соединение нестабильно";
      txt =
        "Подряд неудачных проверок: " +
        String(failStreak) +
        ". Если так продолжается — проверьте процесс ноды или сеть.";
    } else {
      title = "Нода не отвечает";
      txt =
        "Веб-сервер не отвечает. Перезапустите ноду на этом компьютере вручную (установщик, ярлык или служба).";
    }
    btn.setAttribute("aria-label", title);
    btn.title = title;
    body.textContent = txt;
  }
  function ping() {
    var c = new AbortController();
    var timer = setTimeout(function () {
      try {
        c.abort();
      } catch (e) {}
    }, NDL_HEALTH_HTTP_MS);
    fetch("/api/version", {
      credentials: "same-origin",
      cache: "no-store",
      signal: c.signal,
    })
      .then(function (r) {
        clearTimeout(timer);
        if (!r.ok) throw new Error("http");
        return r.json().catch(function () {
          return {};
        });
      })
      .then(function () {
        failStreak = 0;
        stableOkStreak++;
        if (stableOkStreak >= NDL_MIN_OK_STREAK_FOR_DOWN_ALERT) allowDisconnectBanner = true;
        bannerDismissed = false;
        hideDownBanner();
        setTier("ok");
      })
      .catch(function () {
        clearTimeout(timer);
        stableOkStreak = 0;
        failStreak++;
        if (failStreak >= NDL_HEALTH_DEAD_FAILS) {
          setTier("dead");
          if (!HOSTED_MASTER && allowDisconnectBanner && !bannerDismissed) showDownBanner();
        } else setTier("warn");
      });
  }
  setTier("idle");
  hideDownBanner();
  ping();
  setInterval(ping, NDL_HEALTH_POLL_MS);
  function show() {
    tip.hidden = false;
  }
  function hide() {
    tip.hidden = true;
  }
  btn.addEventListener("mouseenter", show);
  btn.addEventListener("mouseleave", hide);
  btn.addEventListener("focusin", show);
  btn.addEventListener("focusout", hide);
}
function initTasksDock(){
  var btn=document.getElementById('dock-tasks-btn');
  var tip=document.getElementById('dock-tasks-tooltip');
  var body=document.getElementById('dock-tasks-tooltip-body');
  var badge=document.getElementById('dock-tasks-badge');
  var overlay=document.getElementById('dock-tasks-panel-overlay');
  var panel=overlay?overlay.querySelector('.dock-tasks-panel'):null;
  var panelBody=document.getElementById('dock-tasks-panel-body');
  var statsWrap=document.getElementById('dock-tasks-panel-stats');
  var statsNums=document.getElementById('dock-tasks-panel-stats-nums');
  var statsBars=document.getElementById('dock-tasks-panel-stats-bars');
  var closeBtn=document.getElementById('dock-tasks-panel-close');
  var refreshBtn=document.getElementById('dock-tasks-panel-refresh');
  var reindexBtn=document.getElementById('dock-tasks-panel-reindex');
  var escBound=null;
  var taskPanelPoll=null;
  var TASK_OVERLAY_LIMIT=25;
  var lastTaskRows=[];
  var lastDonePreview=[];
  var lastTotal=null;
  var lastStatusSnapshot=null;
  var taskSortKey='time';
  var taskSortDir='desc';
  if(!btn||!tip||!body)return;
  if(reindexBtn)reindexBtn.hidden=HOSTED_MASTER;

  function closeTaskPanel(){
    if(!overlay)return;
    overlay.hidden=true;
    overlay.setAttribute('aria-hidden','true');
    btn.setAttribute('aria-expanded','false');
    if(escBound){
      document.removeEventListener('keydown',escBound);
      escBound=null;
    }
    if(taskPanelPoll){
      clearInterval(taskPanelPoll);
      taskPanelPoll=null;
    }
  }
  function openTaskPanel(){
    if(!overlay)return;
    overlay.hidden=false;
    overlay.setAttribute('aria-hidden','false');
    btn.setAttribute('aria-expanded','true');
    tip.hidden=true;
    loadTaskHistory(false);
    if(taskPanelPoll)clearInterval(taskPanelPoll);
    taskPanelPoll=setInterval(function(){
      if(overlay&&!overlay.hidden)loadTaskHistory(true);
    },2000);
    escBound=function(e){if(e.key==='Escape')closeTaskPanel();};
    document.addEventListener('keydown',escBound);
    if(panel){
      try{panel.focus();}catch(err){}
    }
  }
  function toggleTaskPanel(){
    if(!overlay)return;
    if(overlay.hidden)openTaskPanel();else closeTaskPanel();
  }
  function taskTimeValue(t){
    var s=t.finished_at||t.started_at||t.created_at||'';
    if(!s)return 0;
    var ms=Date.parse(s);
    return isNaN(ms)?0:ms;
  }
  function statusTier(t){
    if(typeof t.status_tier==='number')return t.status_tier;
    var s=t.status||'';
    if(s==='processing')return 0;
    if(s==='pending')return 1;
    if(s==='done')return 2;
    if(s==='error')return 3;
    return 4;
  }
  function sortTaskRows(rows,key,dir){
    var arr=rows.slice();
    var mul=dir==='asc'?1:-1;
    arr.sort(function(a,b){
      if(key==='time'){
        return mul*(taskTimeValue(a)-taskTimeValue(b));
      }
      if(key==='status'){
        var ta=statusTier(a),tb=statusTier(b);
        if(ta!==tb)return mul*(ta-tb);
        return mul*(taskTimeValue(a)-taskTimeValue(b));
      }
      if(key==='kind'){
        var ka=String(a.kind||'').localeCompare(String(b.kind||''));
        if(ka!==0)return mul*ka;
        return mul*(taskTimeValue(a)-taskTimeValue(b));
      }
      if(key==='share'){
        var sa=String(a.share_id||'').localeCompare(String(b.share_id||''));
        if(sa!==0)return mul*sa;
        return mul*(taskTimeValue(a)-taskTimeValue(b));
      }
      return 0;
    });
    return arr;
  }
  function getSortedRows(){
    return sortTaskRows(lastTaskRows,taskSortKey,taskSortDir);
  }
  function taskSortIndicator(key){
    if(key!==taskSortKey)return '<span class="task-sort-ind" aria-hidden="true"></span>';
    return '<span class="task-sort-ind" aria-hidden="true">'+(taskSortDir==='asc'?'▲':'▼')+'</span>';
  }
  function thSort(key,label){
    if(!key)return '<th class="task-thumb-th" scope="col">'+label+'</th>';
    var active=key===taskSortKey?' task-sort--active':'';
    var aria=key===taskSortKey?(' aria-sort="'+(taskSortDir==='asc'?'ascending':'descending')+'"'):'';
    return '<th class="task-sort'+active+'" data-sort="'+key+'" scope="col"'+aria+'><span class="task-sort-label">'+label+'</span>'+taskSortIndicator(key)+'</th>';
  }
  function taskStatusPill(t){
    var s=t.status||'';
    var cls='task-pill';
    if(s==='processing')cls+=' task-pill--run';
    else if(s==='pending')cls+=' task-pill--wait';
    else if(s==='done')cls+=' task-pill--ok';
    else if(s==='error')cls+=' task-pill--err';
    return '<span class="'+cls+'">'+esc(s)+'</span>';
  }
  function taskStatusCell(t){
    var pill=taskStatusPill(t);
    if(t.status==='error'&&t.error){
      return '<div class="task-status-stack">'+pill+'<div class="task-cell-err">'+esc(String(t.error).slice(0,160))+'</div></div>';
    }
    return '<div class="task-status-stack">'+pill+'</div>';
  }
  function taskProgressHtml(t){
    var tot=t.progress_total||0;
    var done=t.progress_done||0;
    if(!tot){
      return t.phase?'<span class="meta">'+esc(t.phase)+'</span>':'<span class="meta">—</span>';
    }
    var pct=Math.min(100,Math.round(100*done/tot));
    var phase=t.phase?'<span class="meta"> · '+esc(t.phase)+'</span>':'';
    return '<div class="task-progress"><div class="task-progress-bar" style="width:'+pct+'%"></div></div><span class="task-progress-label">'+esc(String(done)+' / '+String(tot))+'</span>'+phase;
  }
  function taskFileCell(t){
    var full=String(t.payload_summary||'');
    var lab=String(t.file_label||'').trim();
    if(!lab){
      var m=/relative_path=(\S+)/.exec(full);
      if(m)lab=m[1].replace(/^.*[/\\]/,'')||m[1];
    }
    if(!lab&&full)lab=full.slice(0,96);
    if(!lab)lab='—';
    var show=lab.length>44?lab.slice(0,42)+'…':lab;
    return '<span class="task-file-name" title="'+esc(full)+'">'+esc(show)+'</span>';
  }
  function taskRowHtml(t){
    var time=esc(t.finished_at||t.started_at||t.created_at||'');
    var rowClass='task-row';
    if(t.status==='processing')rowClass+=' task-row--active';
    else if(t.status==='pending')rowClass+=' task-row--pending';
    var thumb=t.thumb_url
      ?'<img class="task-thumb" src="'+esc(t.thumb_url)+'" alt="" width="48" height="48" loading="lazy"/>'
      :'<span class="task-thumb-ph meta">—</span>';
    return '<tr class="'+rowClass+'"><td class="task-thumb-cell">'+thumb+'</td><td class="task-status-cell">'+taskStatusCell(t)+'</td><td>'+esc(t.kind)+'</td><td class="task-share-cell">'+esc(t.share_id||'')+'</td><td>'+taskProgressHtml(t)+'</td><td class="task-time">'+time+'</td><td class="task-file-cell">'+taskFileCell(t)+'</td></tr>';
  }
  function taskDoneCardHtml(t){
    var u=t.thumb_url||'';
    var img=u?'<div class="task-done-card-img"><img src="'+esc(u)+'" alt="" loading="lazy"/></div>':'<div class="task-done-card-img task-done-card-img--empty"></div>';
    var lab=t.file_label||'';
    if(!lab&&t.payload_summary)lab=String(t.payload_summary).slice(0,80);
    return '<div class="task-done-card">'+img+'<div class="task-done-card-meta"><span class="task-done-kind">'+esc(t.kind)+'</span><span class="task-done-name" title="'+esc(lab)+'">'+esc(lab||'—')+'</span><span class="meta task-done-time">'+esc(t.finished_at||'')+'</span></div></div>';
  }
  function buildPanelBodyHtml(){
    var rows=getSortedRows();
    var trs=rows.map(function(t){return taskRowHtml(t);}).join('');
    var tableBlock='';
    if(rows.length===0){
      tableBlock='<p class="meta">В срезе «сейчас и очередь» записей нет.</p>';
    }else{
      tableBlock='<div class="task-table-wrap"><table class="task-table"><thead><tr>'+
        thSort(null,'Превью')+
        thSort('status','Статус')+
        thSort('kind','Тип')+
        thSort('share','Шар')+
        '<th scope="col">Прогресс</th>'+
        thSort('time','Время')+
        '<th scope="col">Файл</th>'+
        '</tr></thead><tbody>'+trs+'</tbody></table></div>';
    }
    var doneBlock='';
    if(lastDonePreview.length){
      doneBlock='<div class="task-panel-section task-panel-section--done"><h3 class="task-panel-h3">Последние успешные</h3><p class="meta task-panel-hint">Постеры image_poster и кадр видео — по завершении задачи.</p><div class="task-done-grid">'+lastDonePreview.map(taskDoneCardHtml).join('')+'</div></div>';
    }else{
      doneBlock='<div class="task-panel-section task-panel-section--done"><h3 class="task-panel-h3">Последние успешные</h3><p class="meta">Пока нет завершённых задач с превью.</p></div>';
    }
    return '<div class="task-panel-section"><h3 class="task-panel-h3">Сейчас и очередь</h3>'+tableBlock+'</div>'+doneBlock;
  }
  function renderTaskStats(){
    if(!statsWrap||!statsNums||!statsBars)return;
    if(HOSTED_MASTER){
      statsWrap.hidden=true;
      statsNums.textContent='';
      statsBars.innerHTML='';
      return;
    }
    statsWrap.hidden=false;
    var rows=getSortedRows();
    var totalStr=lastTotal!=null?String(lastTotal):'—';
    var qp=(lastStatusSnapshot&&lastStatusSnapshot.queue_pending)||0;
    var qpr=(lastStatusSnapshot&&lastStatusSnapshot.queue_processing)||0;
    var qsum=qp+qpr;
    statsNums.innerHTML=
      '<div class="dock-tasks-stat-row">'+
      '<span class="dock-tasks-stat"><span class="dock-tasks-stat-num">'+totalStr+'</span><span class="dock-tasks-stat-label">в журнале</span></span>'+
      '<span class="dock-tasks-stat"><span class="dock-tasks-stat-num">'+String(TASK_OVERLAY_LIMIT)+'</span><span class="dock-tasks-stat-label">строк в окне</span></span>'+
      '<span class="dock-tasks-stat"><span class="dock-tasks-stat-num">'+String(lastDonePreview.length)+'</span><span class="dock-tasks-stat-label">успешных с превью</span></span>'+
      '<span class="dock-tasks-stat"><span class="dock-tasks-stat-num">'+String(qsum)+'</span><span class="dock-tasks-stat-label">в очереди</span></span>'+
      '</div>';
    var queueBar='';
    if(qsum>0){
      var wRun=(qpr/qsum)*100;
      var wWait=(qp/qsum)*100;
      queueBar='<div class="dock-tasks-bar-group"><div class="dock-tasks-bar-caption">Очередь сервера</div><div class="dock-tasks-mix-bar" role="img" aria-label="Выполняется '+qpr+', ожидает '+qp+'">'+
        '<div class="dock-tasks-mix-seg dock-tasks-mix-seg--run" style="width:'+wRun+'%"></div>'+
        '<div class="dock-tasks-mix-seg dock-tasks-mix-seg--wait" style="width:'+wWait+'%"></div>'+
        '</div></div>';
    }else{
      queueBar='<div class="dock-tasks-bar-group"><div class="dock-tasks-bar-caption meta">Очередь пуста</div><div class="dock-tasks-mix-bar dock-tasks-mix-bar--idle"></div></div>';
    }
    var sliceBar='';
    var n=rows.length;
    if(n>0){
      var C={done:0,pending:0,processing:0,error:0};
      rows.forEach(function(t){
        var s=t.status||'';
        if(s==='done')C.done++;
        else if(s==='pending')C.pending++;
        else if(s==='processing')C.processing++;
        else if(s==='error')C.error++;
      });
      var pct=function(c){return (c/n)*100;};
      sliceBar='<div class="dock-tasks-bar-group"><div class="dock-tasks-bar-caption">Срез таблицы</div><div class="dock-tasks-mix-bar" role="img" aria-label="По статусам в текущем списке">'+
        (C.processing>0?'<div class="dock-tasks-mix-seg dock-tasks-mix-seg--run" style="width:'+pct(C.processing)+'%"></div>':'')+
        (C.pending>0?'<div class="dock-tasks-mix-seg dock-tasks-mix-seg--wait" style="width:'+pct(C.pending)+'%"></div>':'')+
        (C.done>0?'<div class="dock-tasks-mix-seg dock-tasks-mix-seg--ok" style="width:'+pct(C.done)+'%"></div>':'')+
        (C.error>0?'<div class="dock-tasks-mix-seg dock-tasks-mix-seg--err" style="width:'+pct(C.error)+'%"></div>':'')+
        '</div></div>';
    }else{
      sliceBar='<div class="dock-tasks-bar-group"><p class="meta dock-tasks-bar-empty">Нет строк в таблице</p></div>';
    }
    var journalPct=lastTotal>0?Math.min(100,Math.round((100*Math.min(rows.length,TASK_OVERLAY_LIMIT))/lastTotal)):0;
    var journalTrack='<div class="dock-tasks-bar-group"><div class="dock-tasks-bar-caption">Показано от журнала</div><div class="dock-tasks-journal-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'+journalPct+'"><div class="dock-tasks-journal-fill" style="width:'+journalPct+'%"></div></div><div class="dock-tasks-journal-hint meta">'+
      (lastTotal!=null?String(rows.length)+' из '+String(lastTotal):'')+
      '</div></div>';
    statsBars.innerHTML=queueBar+sliceBar+journalTrack;
  }
  function renderTaskPanelBody(){
    if(!panelBody)return;
    panelBody.innerHTML=buildPanelBodyHtml();
    renderTaskStats();
  }
  function loadTaskHistory(quiet){
    if(!panelBody)return;
    if(HOSTED_MASTER){
      panelBody.innerHTML='<p class="meta">Очередь задач доступна только на процессе ноды.</p>';
      if(statsWrap)statsWrap.hidden=true;
      return;
    }
    if(!quiet)panelBody.innerHTML='<p class="meta">Загрузка…</p>';
    var url='/api/tasks/history?limit='+String(TASK_OVERLAY_LIMIT)+'&offset=0&sort=priority&done_limit=12';
    var p1=fetchJson(url);
    var p2=fetchJson('/api/tasks/status').catch(function(){return null;});
    Promise.all([p1,p2]).then(function(pair){
      var d=pair[0];
      var st=pair[1];
      if(!d||!d.ok)return;
      lastTaskRows=(d.tasks||[]).slice();
      lastDonePreview=(d.recent_done||[]).slice();
      lastTotal=d.total!=null?d.total:null;
      lastStatusSnapshot=st&&st.ok?st:null;
      renderTaskPanelBody();
    }).catch(function(e){
      if(!quiet)panelBody.innerHTML='<p class="meta">'+esc(e.message||'Ошибка загрузки')+'</p>';
    });
  }

  if(panelBody){
    panelBody.addEventListener('click',function(e){
      var th=e.target.closest('th.task-sort');
      if(!th||!panelBody.contains(th))return;
      var key=th.getAttribute('data-sort');
      if(!key)return;
      e.preventDefault();
      if(key===taskSortKey){
        taskSortDir=taskSortDir==='asc'?'desc':'asc';
      }else{
        taskSortKey=key;
        taskSortDir=key==='time'?'desc':'asc';
      }
      renderTaskPanelBody();
    });
  }

  btn.addEventListener('click',function(e){
    e.preventDefault();
    e.stopPropagation();
    toggleTaskPanel();
  });
  if(overlay){
    overlay.addEventListener('click',function(e){
      if(e.target===overlay)closeTaskPanel();
    });
  }
  if(panel){
    panel.addEventListener('click',function(e){e.stopPropagation();});
  }
  if(closeBtn)closeBtn.addEventListener('click',closeTaskPanel);
  if(refreshBtn)refreshBtn.addEventListener('click',function(){loadTaskHistory(false);});
  if(reindexBtn){
    reindexBtn.addEventListener('click',function(){
      if(HOSTED_MASTER)return;
      fetchJson('/api/tasks/reindex-all',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
        .then(function(d){
          var n=d&&d.enqueued!=null?d.enqueued:0;
          toast('В очереди переиндексация: '+n+' шар(ов)','success');
          loadTaskHistory(false);
        })
        .catch(function(e){toast(e.message||'Ошибка','err');});
    });
  }

  function poll(){
    fetch('/api/tasks/status',{credentials:'same-origin'}).then(function(r){
      return r.json().then(function(d){return {ok:r.ok,status:r.status,d:d};}).catch(function(){return {ok:r.ok,status:r.status,d:null};});
    }).then(function(x){
      var d=x.d;
      if(!x.ok||!d||!d.ok){
        var msg=HOSTED_MASTER
          ?'Очередь задач доступна только на процессе ноды.'
          :(d&&d.error)
            ?String(d.error)
            :('Нода недоступна (HTTP '+x.status+').');
        body.textContent=msg;
        if(badge)badge.hidden=true;
        updateFoldersQueueHint({ok:false});
        return;
      }
      var qp=d.queue_pending||0;
      var qpr=d.queue_processing||0;
      var q=qp+qpr;
      if(badge){
        badge.textContent=String(q);
        badge.hidden=q===0;
      }
      var lines=[];
      var cur=d.current;
      if(cur){
        lines.push('Тип: '+String(cur.kind||''));
        lines.push('Прогресс: '+(cur.progress_done||0)+' / '+(cur.progress_total||0));
        if(cur.phase)lines.push('Фаза: '+cur.phase);
        if(cur.share_id)lines.push('Шара: '+cur.share_id);
      }else{
        lines.push('Нет активной задачи');
      }
      lines.push('В очереди: '+qp);
      if(d.eta_seconds!=null&&d.eta_seconds!=='')lines.push('ETA ~ '+d.eta_seconds+' с');
      var lf=d.last_failed;
      if(lf&&lf.error){
        lines.push('Последняя ошибка: '+String(lf.error).slice(0,200));
      }
      lines.push('Клик — окно задач по центру экрана.');
      body.textContent=lines.join('\n');
      updateFoldersQueueHint(d);
    }).catch(function(){
      body.textContent=HOSTED_MASTER?'Очередь задач доступна только на процессе ноды.':'Нет соединения с нодой.';
      if(badge)badge.hidden=true;
      updateFoldersQueueHint({ok:false});
    });
  }
  poll();
  setInterval(poll,1500);
  function show(){if(overlay&&!overlay.hidden)return;tip.hidden=false;}
  function hide(){tip.hidden=true;}
  btn.addEventListener('mouseenter',show);
  btn.addEventListener('mouseleave',hide);
  btn.addEventListener('focusin',show);
  btn.addEventListener('focusout',hide);
}
function initDock(){
  var g=document.getElementById('dock-auth-guest');
  var wrap=document.getElementById('dock-auth-owner-wrap');
  if(IS_OWNER){
    if(g)g.hidden=true;
    if(wrap)wrap.hidden=false;
  }else{
    if(g)g.hidden=false;
    if(wrap)wrap.hidden=true;
  }
  initDockDropdown();
}
async function init(){
  restoreApplyUpgradeReportFromStorage();
  const h=location.hostname;
  LOOPBACK=(h==='127.0.0.1'||h==='localhost');
  try{
    const r=await fetch('/api/me',{credentials:'same-origin'});
    if(r.ok){
      const me=await r.json();
      if(me&&me.authenticated){
        IS_OWNER=true;
        OWNER_SUB=String(me.sub||'');
        applyDockAvatar(me);
        const op=document.getElementById('owner-panel');
        const td=document.getElementById('tile-data');
        if(op)op.hidden=false;
        if(td)td.hidden=false;
        const tg=document.getElementById('tile-grid');
        if(tg)tg.classList.add('has-data');
        const ne=document.getElementById('owner-name');
        if(ne)ne.textContent=me.username||me.email||'';
        const sub=document.getElementById('sub');
        if(sub)sub.textContent=me.username||me.email||'нода';
      }
    }
  }catch(e){}
  if(!IS_OWNER){
    const op=document.getElementById('owner-panel');
    const td=document.getElementById('tile-data');
    if(op)op.hidden=true;
    if(td)td.hidden=true;
    const tg=document.getElementById('tile-grid');
    if(tg)tg.classList.remove('has-data');
  }
  CAN_PORT=LOOPBACK||IS_OWNER;
  const nm=document.getElementById('net-man');
  if(nm)nm.hidden=!CAN_PORT;
  const nar=document.getElementById('net-actions-row');
  if(nar)nar.hidden=!CAN_PORT;
  await loadVer();
  applyFolderPanelVisibility();
  updatePortRemoteMsg(null);
  (function ensureMarketplaceStripBottom(){
    var strip=document.getElementById('marketplace-strip');
    var foot=document.querySelector('.wrap > .footer-link');
    if(!strip||!foot||strip.parentNode!==foot.parentNode)return;
    foot.parentNode.insertBefore(strip,foot);
  })();
  initMarketplaceToggle();
  initPerfOverlay();
  initTooltips();
  initStorageUi();
  initTiles();
  window.addEventListener('resize',function(){
    var pan=document.getElementById('panel-storage');
    if(pan&&!pan.hidden)redrawActiveStorageCharts();
  });
  initDock();
  initDockHealth();
  initDiskBench();
  initSystemUpgrade();
  initTasksDock();
  loadNet();loadStats();loadEdgeVersion();loadShares();loadPubs();loadTor();loadMed();
  setTimeout(function(){ pollSiteChannel(); },1500);
  setInterval(pollSiteChannel,30000);
  setInterval(function(){
    loadVer().then(applyFolderPanelVisibility);
    loadNet();loadStats();loadTor();loadMed();
    var mexp=document.getElementById('marketplace-expanded');
    if(mexp&&!mexp.hidden&&!HOSTED_MASTER)loadMarketplace(undefined,true);
  },5000);
  setInterval(loadEdgeVersion,60000);
}
document.addEventListener('DOMContentLoaded',function(){init().catch(function(e){console.error(e);});});