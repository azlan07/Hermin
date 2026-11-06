const byId = (id) => document.getElementById(id);
let webCsrf = '';
let pending = false;
async function webApi(action) {
  const response = await fetch(action ? '/api/action' : '/api/opencode/web', action ? {
    method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':webCsrf},
    body:JSON.stringify({action:`opencode-${action}`})
  } : {});
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function message(text) { byId('web-message').textContent=text; byId('web-message').hidden=!text; }
async function status() {
  const data = await webApi(); webCsrf=data.csrf;
  byId('web-status').textContent = data.conflict ? 'Port 4096 dipakai layanan lain' : `127.0.0.1:4096 · ${data.running?'aktif':'berhenti'}`;
  byId('web-start').hidden=data.running;
  byId('web-stop').hidden=!data.running;
  byId('web-restart').hidden=!data.running;
}
function confirmAction(action) {
  byId('confirm-title').textContent=action==='stop'?'Hentikan OpenCode?':'Restart OpenCode?';
  byId('confirm-description').textContent='Koneksi OpenCode Web dan CLI yang memakai server ini akan terputus. Riwayat tersimpan tetap ada.';
  const dialog=byId('web-confirm'); dialog.returnValue=''; dialog.showModal();
  return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='yes'),{once:true}));
}
byId('confirm-no').onclick=()=>byId('web-confirm').close('no');
byId('confirm-yes').onclick=()=>byId('web-confirm').close('yes');
async function act(action, external=false) {
  if(pending)return;
  pending=true;
  if(['stop','restart'].includes(action) && !(await confirmAction(action))){pending=false;return;}
  // Reserve the tab during the click so browser popup blockers do not swallow it.
  const tab=external?window.open('about:blank','_blank'):null;
  if(tab)tab.opener=null;
  document.querySelectorAll('nav button').forEach(b=>b.disabled=true);
  try {
    message(''); await status();
    const data=await webApi(action);
    if(action==='open'){
      const url=new URL(data.url);
      if(url.origin!=='http://127.0.0.1:4096'||!url.pathname.startsWith('/auth/connect/'))throw new Error('Tautan login tidak valid.');
      if(external){if(!tab)throw new Error('Izinkan popup untuk membuka OpenCode di tab baru.');tab.location.replace(data.url);}
      else {byId('web-frame').src=data.url;byId('web-frame').hidden=false;byId('web-placeholder').hidden=true;}
    } else {
      message(data.message);
      if(action==='stop'||action==='restart'){byId('web-frame').removeAttribute('src');byId('web-frame').hidden=true;byId('web-placeholder').hidden=false;}
    }
    await status();
  } catch(error){if(tab)tab.close();message(error.message);}
  finally {pending=false;document.querySelectorAll('nav button').forEach(b=>b.disabled=false);}
}
byId('web-connect').onclick=()=>act('open');
byId('web-external').onclick=()=>act('open',true);
for(const action of ['start','stop','restart'])byId(`web-${action}`).onclick=()=>act(action);
status().then(()=>{if(new URLSearchParams(location.search).get('autostart')==='1')act('open');}).catch(e=>message(e.message));
// Status refresh never changes the iframe URL or interrupts a conversation.
setInterval(()=>{if(!pending)status().catch(e=>message(e.message));},30000);
