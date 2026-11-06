const $ = (id) => document.getElementById(id);
let csrf = '';
let current = null;
let isEnvOpen = false;
let confirmResolver = null;
let confirmTrigger = null;
let activeProvider = 'custom';
let modelSelections = {custom:'', nous:''};
let opencodeData = null;

function notice(message, kind = 'success') {
  const root = $('toast-stack');
  const toast = document.createElement('div');
  toast.className = `toast ${kind}`;
  const icon = document.createElement('span'); icon.className = 'toast-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = kind === 'error' ? '!' : (kind === 'success' ? '✓' : 'i');
  const copy = document.createElement('span'); copy.textContent = message;
  const close = document.createElement('button'); close.type = 'button'; close.className = 'toast-close'; close.textContent = '×'; close.setAttribute('aria-label', 'Tutup notifikasi');
  close.addEventListener('click', () => toast.remove());
  toast.append(icon, copy, close); root.append(toast);
  window.setTimeout(() => { toast.classList.add('leaving'); window.setTimeout(() => toast.remove(), 250); }, 5200);
}

function confirmDialog({title, message, confirmLabel = 'Lanjutkan', danger = false}) {
  $('modal-title').textContent = title;
  $('modal-copy').textContent = message;
  $('modal-confirm').textContent = confirmLabel;
  $('modal-confirm').classList.toggle('danger', danger);
  confirmTrigger = document.activeElement;
  document.querySelector('.shell').inert = true;
  $('confirm-modal').hidden = false;
  $('modal-confirm').focus();
  return new Promise((resolve) => { confirmResolver = resolve; });
}

function settleConfirm(value) {
  $('confirm-modal').hidden = true;
  if (confirmResolver) confirmResolver(value);
  confirmResolver = null;
  document.querySelector('.shell').inert = false;
  confirmTrigger?.focus();
}

async function api(url, body) {
  const options = { headers: {} };
  if (body !== undefined) {
    options.method = 'POST';
    options.headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function pill(id, text, good) {
  const el = $(id);
  el.textContent = text;
  el.className = `status-pill ${good ? '' : 'off'}`;
}

function updateEditor(id, value) {
  const editor = $(id);
  if (!editor.dataset.dirty) editor.value = value;
  updateEditorStatus(editor);
}

function updateEditorStatus(editor) {
  const name = editor.id.replace(/-editor$/, '');
  if ($(`${name}-count`)) $(`${name}-count`).textContent = `${editor.value.length.toLocaleString('id-ID')} karakter`;
  if ($(`${name}-save-state`)) $(`${name}-save-state`).textContent = editor.dataset.dirty ? 'Belum disimpan' : 'Tersimpan';
}

function renderPrivacy(security) {
  const native = security.mode === 'native';
  const mode = native ? 'NATIVE · TANPA SANDBOX' : security.mode === 'sandbox' ? 'SANDBOX MASIH AKTIF' : 'MODE BELUM TERBACA';
  $('native-mode').textContent = mode;
  $('privacy-mode').textContent = mode;
  $('native-summary').textContent = security.policy_installed
    ? 'Soul & memory meminta persetujuan sebelum akses. Pembatas teknis folder tidak aktif pada mode native.'
    : 'Instruksi privasi belum lengkap. Terapkan ulang aturan dari menu Privasi.';
  $('privacy-approval').textContent = security.approval_mode === 'manual' ? 'Manual · tanya untuk perintah berisiko' : `Perlu dicek · ${security.approval_mode}`;
  $('privacy-install').textContent = security.lazy_installs ? 'Aktif · perlu dinonaktifkan' : 'Dinonaktifkan';
  $('privacy-secrets').textContent = security.redact_secrets ? 'Aktif' : 'Tidak aktif';
  $('privacy-documents').textContent = security.policy_installed ? 'Soul, memory & profil tersedia' : 'Belum lengkap';
}

function renderUsage(usage) {
  const available = !!usage?.available;
  const input = available ? Number(usage.prompt_tokens || 0) : 0;
  const output = available ? Number(usage.completion_tokens || 0) : 0;
  const total = input + output;
  const compact = (value) => new Intl.NumberFormat('id-ID', {notation:'compact', maximumFractionDigits:1}).format(value);
  const exact = (value) => new Intl.NumberFormat('id-ID').format(value);
  const cost = available ? Number(usage.estimated_cost_usd || 0) : 0;
  $('usage-tokens').textContent = available ? compact(total) : '—';
  $('usage-token-exact').textContent = available ? `${exact(total)} token input + output` : 'Statistik belum tersedia';
  $('usage-cost').textContent = available ? new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', minimumFractionDigits:2, maximumFractionDigits:cost > 0 && cost < 0.01 ? 4 : 2}).format(cost) : '—';
  $('usage-requests').textContent = available ? exact(Number(usage.requests || 0)) : '—';
  $('usage-input').textContent = available ? `Input ${compact(input)}` : 'Input —';
  $('usage-output').textContent = available ? `Output ${compact(output)}` : 'Output —';
  $('usage-input-bar').style.width = total ? `${input / total * 100}%` : '0%';
  $('usage-output-bar').style.width = total ? `${output / total * 100}%` : '0%';
  $('usage-top-model').textContent = available ? (usage.top_model || 'Belum ada') : '—';
  $('usage-note').textContent = available ? 'Estimasi nilai API setara dari seluruh trafik 9Router; bukan tagihan.' : (usage?.error || 'Statistik belum tersedia.');
}

function renderModels(models = []) {
  const list = $('model-list');
  const normalized = models.map((model) => typeof model === 'string' ? {id:model,label:model,kind:'model',provider:'',detail:''} : model);
  const isCombo = (model) => String(model.kind).toLowerCase().includes('combo') || String(model.id).toLowerCase().startsWith('combo/');
  if ($('provider').value === 'custom') renderModelOptions(normalized, current?.model?.default);
  $('model-count').textContent = normalized.length;
  if (!normalized.length) {
    list.innerHTML = '<div class="empty-state">Belum ada model terbaca. Cek status 9Router dan API key.</div>';
    return;
  }
  list.replaceChildren();
  normalized.slice(0, 8).forEach((model) => {
    const row = document.createElement('div'); row.className = 'model-row';
    const name = document.createElement('span'); name.textContent = `${isCombo(model) ? 'COMBO · ' : ''}${model.id}`;
    const choose = document.createElement('button'); choose.textContent = 'Pakai'; choose.type = 'button';
    choose.addEventListener('click', () => { $('provider').value = 'custom'; toggleProvider(); $('model-id').value = model.id; modelSelections.custom = model.id; showPage('model'); });
    row.append(name, choose); list.append(row);
  });
  if (normalized.length > 8) {
    const rest = document.createElement('div'); rest.className = 'empty-state'; rest.textContent = `+ ${normalized.length - 8} pilihan lain tersedia di dropdown.`; list.append(rest);
  }
}

function renderModelOptions(models = [], selected = '') {
  const select = $('model-id');
  const normalized = models.map((model) => typeof model === 'string' ? {id:model,label:model,kind:'model'} : model);
  const isCombo = (model) => String(model.kind).toLowerCase().includes('combo') || String(model.id).toLowerCase().startsWith('combo/');
  const value = selected;
  const isNous = $('provider').value === 'nous';
  select.replaceChildren();
  const visible = isNous && $('nous-free-only').checked ? normalized.filter((model) => model.tier === 'free') : normalized;
  const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = visible.length ? 'Pilih model…' : (isNous ? 'Model gratis belum terverifikasi — muat ulang' : 'Katalog belum tersedia'); select.append(placeholder);
  const groups = isNous
    ? [['Gratis · Nous Portal', visible.filter((model) => model.tier === 'free')],
       ['Harga belum terverifikasi', visible.filter((model) => model.tier === 'unknown')],
       ['Berbayar', visible.filter((model) => model.tier === 'paid')]]
    : [['Combo 9Router', visible.filter(isCombo)], ['Model', visible.filter((model) => !isCombo(model))]];
  for (const [groupName, items] of groups) {
    if (!items.length) continue;
    const group = document.createElement('optgroup'); group.label = groupName;
    items.forEach((model) => { const option = document.createElement('option'); option.value = model.id; option.textContent = model.label === model.id ? model.id : `${model.label} · ${model.id}`; if (model.detail) option.title = model.detail; group.append(option); });
    select.append(group);
  }
  const hiddenByFreeFilter = isNous && $('nous-free-only').checked && !visible.some((model) => model.id === value);
  if (value && !visible.some((model) => model.id === value) && !hiddenByFreeFilter) {
    const selectedModel = normalized.find((model) => model.id === value);
    const fallback = document.createElement('option'); fallback.value = value;
    fallback.textContent = `${value} · ${selectedModel?.tier === 'paid' ? 'berbayar' : 'model aktif / belum terverifikasi'}`;
    select.append(fallback);
  }
  select.value = hiddenByFreeFilter ? '' : (value || '');
}

function populate(data) {
  current = data; csrf = data.csrf;
  const online = !!data.hermes.running;
  $('opencode-web-summary').textContent = data.opencode_web?.conflict ? 'Port 4096 dipakai layanan lain' : `127.0.0.1:4096 · ${data.opencode_web?.running ? 'Aktif' : 'Berhenti — klik Buka untuk menyalakan'}`;
  pill('hermes-pill', online ? 'RUNNING' : 'STOPPED', online);
  $('hermes-status').textContent = online ? 'Aktif' : 'Berhenti';
  const service = (data.hermes.services || []).find((x) => x.Service === 'hermes');
  const dashboard = (data.hermes.services || []).find((x) => x.Service === 'dashboard');
  $('hermes-detail').textContent = service ? `Gateway ${service.State || 'unknown'} · Dashboard ${dashboard?.State || 'unknown'}` : (data.hermes.output || 'systemd user service');
  $('hero-state').textContent = online ? 'Hermes sedang berjalan' : 'Hermes sedang berhenti';
  $('hero-state').previousElementSibling.className = online ? 'pulse' : '';
  document.querySelectorAll('[data-action="start"]').forEach((button) => { button.hidden = online; });
  document.querySelectorAll('[data-action="restart"], [data-action="stop"]').forEach((button) => { button.hidden = !online; });
  document.querySelectorAll('[data-action="shutdown"]').forEach((button) => { button.hidden = !data.security?.autostart; });
  pill('router-pill', data.router.ok ? 'CONNECTED' : 'OFFLINE', data.router.ok);
  $('router-status').textContent = data.router.ok ? 'Terhubung' : 'Tidak tersambung';
  $('router-detail').textContent = data.router.ok ? `${data.router.count} model tersedia` : (data.router.error || data.router.url);
  $('router-service-state').textContent = `${data.router_service?.state || 'unknown'} ${data.router_service?.detail || ''}`;
  const routerOnline = !!data.router_service?.running;
  document.querySelectorAll('[data-router-action="start"]').forEach((button) => { button.hidden = routerOnline; });
  document.querySelectorAll('[data-router-action="restart"], [data-router-action="stop"]').forEach((button) => { button.hidden = !routerOnline; });
  document.querySelectorAll('[data-router-action="shutdown"]').forEach((button) => { button.hidden = !data.router_service?.enabled; });
  $('router-power-state').textContent = routerOnline ? 'RUNNING' : (data.router_service?.enabled ? 'STOPPED' : 'SHUTDOWN');
  $('router-service-logs').hidden = true;
  const model = data.model || {};
  const is9router = model.provider === 'custom';
  $('model-status').textContent = model.default || 'Belum dipilih';
  $('model-detail').textContent = is9router ? '9Router · custom endpoint' : `${model.provider || 'Provider'} · model utama`;
  pill('key-pill', data.secrets.api_key_set ? 'KEY SET' : 'NO KEY', !!data.secrets.api_key_set);
  $('route-model').textContent = model.default || 'belum dipilih';
  $('route-provider').textContent = is9router ? '9Router · custom endpoint' : (model.provider === 'nous' ? 'Nous Portal' : model.provider || 'Provider');
  $('route-url').textContent = is9router ? model.base_url : 'OAuth provider';
  $('services-status').textContent = data.config_error ? 'Config bermasalah' : (data.files_present.services && data.files_present.config ? 'Lengkap' : 'Perlu dicek');
  $('services-detail').textContent = data.config_error ? data.config_error.slice(0, 70) : 'Unit systemd + config.yaml ditemukan';
  pill('services-pill', data.config_error ? 'CHECK' : 'READY', !data.config_error);
  modelSelections = {custom: '', nous: ''};
  modelSelections[model.provider === 'nous' ? 'nous' : 'custom'] = model.default || '';
  activeProvider = model.provider === 'nous' ? 'nous' : 'custom';
  $('provider').value = model.provider === 'nous' ? 'nous' : 'custom';
  $('base-url').value = model.base_url || 'http://127.0.0.1:20128/v1';
  $('model-id').value = model.default || '';
  toggleProvider();
  $('model-connection-title').textContent = data.router.ok ? '9Router tersambung' : 'Belum tersambung';
  $('model-connection-copy').textContent = data.router.ok ? `${data.router.count} model terbaca dari ${data.router.url}.` : (data.router.error || `Mencoba ${data.router.url}`);
  $('api-key-status').textContent = data.secrets.api_key_set ? 'Tersimpan' : 'Belum diisi';
  $('router-api-key').placeholder = data.secrets.api_key_set ? 'Tersimpan — isi hanya untuk mengganti' : 'Masukkan API key 9Router';
  $('router-key-help').textContent = data.secrets.api_key_set ? 'Key lama tetap dipakai jika kolom ini kosong. Key baru disimpan di hermes/data/.env.' : 'Key disimpan di hermes/data/.env dan tidak ditampilkan kembali oleh dashboard.';
  $('env-key-title').textContent = data.secrets.api_key_set ? 'API key sudah diatur' : 'API key belum diatur';
  $('env-base-url').textContent = data.environment.OPENAI_BASE_URL || 'Tidak diatur di .env';
  updateEditor('service-hermes-editor', data.files.service_hermes || '');
  updateEditor('service-dashboard-editor', data.files.service_dashboard || '');
  updateEditor('service-router-editor', data.files.service_router || '');
  updateEditor('soul-editor', (data.texts || {}).soul || '');
  updateEditor('memory-editor', (data.texts || {}).memory || '');
  updateEditor('user-memory-editor', (data.texts || {}).user_memory || '');
  renderModels(data.router.models || []);
  if ($('usage-period').value === '24h') renderUsage(data.usage);
  renderPrivacy(data.security || {});
  $('last-refresh').textContent = `Diperbarui ${new Date().toLocaleTimeString('id-ID', {hour:'2-digit', minute:'2-digit'})}`;
  if (data.router.error) $('router-detail').title = data.router.error;
}

function toggleProvider() {
  const provider = $('provider').value;
  if (activeProvider !== provider) {
    modelSelections[activeProvider] = $('model-id').value;
    activeProvider = provider;
  }
  const isCustom = provider === 'custom';
  $('custom-fields').hidden = !isCustom;
  $('nous-free-filter').hidden = isCustom;
  $('model-label').textContent = isCustom ? 'Model / combo tersedia' : 'Model Nous Portal';
  $('model-help').textContent = isCustom ? 'Model harus tersedia/aktif di 9Router.' : 'Model gratis didahulukan. Statusnya mengikuti cache harga dan rekomendasi Portal.';
  const models = isCustom ? (current?.router?.models || []) : (current?.nous_models || []);
  const selected = modelSelections[provider] || (current?.model?.provider === provider ? current.model.default : '');
  renderModelOptions(models, selected);
  if (!isCustom) {
    const free = models.filter((model) => model.tier === 'free').length;
    $('model-help').textContent = `${free} model bertarif nol dari ${models.length} pilihan. Status dari cache Hermes/Portal maksimal 24 jam; akses dan kuota tetap mengikuti akunmu. Tekan Muat ulang untuk data terbaru.`;
  }
  document.querySelectorAll('.quick-choice').forEach((button) => button.classList.toggle('selected', button.dataset.provider === $('provider').value));
}

function opencodeModelOptions(select, selected, automaticLabel = '') {
  select.replaceChildren();
  if (automaticLabel) {
    const automatic = document.createElement('option'); automatic.value = '';
    automatic.textContent = automaticLabel; select.append(automatic);
  }
  const groups = new Map();
  for (const model of opencodeData?.models || []) {
    if (!groups.has(model.provider)) {
      const group = document.createElement('optgroup'); group.label = model.provider;
      groups.set(model.provider, group); select.append(group);
    }
    const option = document.createElement('option'); option.value = model.id;
    option.textContent = `${model.label} · ${model.id}${model.available ? '' : ' (tidak ada di katalog)'}`;
    groups.get(model.provider).append(option);
  }
  if (selected && !(opencodeData?.models || []).some((item) => item.id === selected)) {
    const option = document.createElement('option'); option.value = selected;
    option.textContent = `${selected} · tersimpan, belum ada di katalog`;
    select.append(option);
  }
  select.value = selected || '';
}

function renderOpencodeAgent() {
  const selected = (opencodeData?.agents || []).find((item) => item.id === $('opencode-agent').value);
  opencodeModelOptions($('opencode-agent-model'), selected?.model || '', 'Ikuti model utama');
  $('opencode-agent-model').disabled = !selected;
}

async function loadOpencode() {
  $('refresh-opencode').disabled = true;
  $('opencode-status').textContent = 'Memeriksa…';
  try {
    const data = await api('/api/opencode');
    if (!data.ok) throw new Error(data.error || 'Konfigurasi OpenCode gagal dibaca.');
    opencodeData = data;
    opencodeModelOptions($('opencode-main-model'), data.model);
    opencodeModelOptions($('opencode-small-model'), data.small_model, 'Ikuti pilihan otomatis OpenCode');
    const agents = $('opencode-agent'); agents.replaceChildren();
    const empty = document.createElement('option'); empty.value = ''; empty.textContent = 'Tidak ada agent khusus'; agents.append(empty);
    for (const agent of data.agents) {
      const option = document.createElement('option'); option.value = agent.id; option.textContent = agent.id; agents.append(option);
    }
    agents.value = data.agents[0]?.id || '';
    renderOpencodeAgent();
    $('opencode-router-url').textContent = data.router.base_url;
    $('opencode-status').textContent = data.router.ok ? 'OpenCode & 9Router siap' : 'OpenCode terbaca · 9Router perlu dicek';
    $('opencode-status-copy').textContent = data.router.ok
      ? `${data.router.count} model / combo tersedia dari 9Router.`
      : (data.router.error || 'Katalog 9Router belum bisa dimuat.');
    $('save-opencode').disabled = !data.models.length;
  } catch (error) {
    opencodeData = null;
    $('opencode-status').textContent = 'Konfigurasi belum siap';
    $('opencode-status-copy').textContent = error.message;
    $('save-opencode').disabled = true;
    notice(error.message, 'error');
  } finally { $('refresh-opencode').disabled = false; }
}

function showPage(name) {
  document.querySelectorAll('.nav-item').forEach((el) => el.classList.toggle('active', el.dataset.page === name));
  document.querySelectorAll('.page').forEach((el) => el.classList.toggle('active', el.id === `page-${name}`));
  const titles = {skills:'Skill manager', overview:'Ringkasan', model:'Model & koneksi', opencode:'OpenCode', memory:'Soul & memory', privacy:'Privasi', services:'Layanan native', env:'Environment'};
  $('page-title').textContent = titles[name] || 'Dashboard';
  if (name === 'opencode') loadOpencode();
  if (name === 'skills') window.loadSkills?.();
  window.scrollTo({top:0, behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
}

async function refresh() {
  $('refresh').disabled = true;
  try { populate(await api('/api/state')); if ($('usage-period').value !== '24h') await loadUsage(); }
  catch (error) { notice(`Gagal memuat status: ${error.message}`, 'error'); }
  finally { $('refresh').disabled = false; }
}

async function loadUsage() {
  $('refresh-usage').disabled = true;
  try { renderUsage(await api(`/api/usage?period=${encodeURIComponent($('usage-period').value)}`)); }
  catch (error) { renderUsage({available:false, error:`Statistik gagal dimuat: ${error.message}`}); }
  finally { $('refresh-usage').disabled = false; }
}

async function action(name, successText) {
  const buttons = [...document.querySelectorAll('[data-action]')]; buttons.forEach((b) => b.disabled = true);
  notice(name === 'stop' ? 'Menghentikan Hermes…' : 'Menjalankan layanan systemd…', '');
  try {
    const result = await api('/api/action', { action: name });
    if (!result.ok) throw new Error(result.stderr || result.error || 'Perintah gagal.');
    notice(successText, 'success');
    if (name === 'logs') $('logs').textContent = result.stdout || '(log kosong)';
    await refresh();
  } catch (error) { notice(error.message, 'error'); }
  finally { buttons.forEach((b) => b.disabled = false); }
}

async function save(payload, successFallback, editorId) {
  try {
    const result = await api('/api/action', payload);
    if (!result.ok) throw new Error(result.error || result.stderr || 'Gagal menyimpan.');
    notice(result.message || successFallback, 'success');
    if (editorId && $(editorId).value === payload.text) delete $(editorId).dataset.dirty;
    await refresh();
    return true;
  } catch (error) { notice(error.message, 'error'); return false; }
}

document.querySelectorAll('[data-page]').forEach((el) => el.addEventListener('click', () => showPage(el.dataset.page)));
$('refresh').addEventListener('click', refresh);
$('refresh-opencode').addEventListener('click', loadOpencode);
$('opencode-agent').addEventListener('change', renderOpencodeAgent);
$('save-opencode').addEventListener('click', async () => {
  $('save-opencode').disabled = true;
  try {
    const result = await api('/api/action', {action:'save-opencode-models',
      model:$('opencode-main-model').value, small_model:$('opencode-small-model').value,
      agent_name:$('opencode-agent').value, agent_model:$('opencode-agent-model').value});
    notice(result.message || 'Model OpenCode disimpan.', 'success');
    await loadOpencode();
  } catch (error) { notice(error.message, 'error'); $('save-opencode').disabled = false; }
});
$('usage-period').addEventListener('change', loadUsage);
$('refresh-usage').addEventListener('click', loadUsage);
$('provider').addEventListener('change', toggleProvider);
$('model-id').addEventListener('change', () => { modelSelections[$('provider').value] = $('model-id').value; });
$('nous-free-only').addEventListener('change', () => renderModelOptions(current?.nous_models || [], modelSelections.nous || $('model-id').value));
document.querySelectorAll('.quick-choice').forEach((button) => button.addEventListener('click', () => {
  $('provider').value = button.dataset.provider;
  if (button.dataset.provider === 'custom') $('base-url').value = current?.model?.base_url || 'http://127.0.0.1:20128/v1';
  toggleProvider();
}));
document.querySelectorAll('[data-action]').forEach((el) => el.addEventListener('click', async () => {
  const actionName = el.dataset.action;
  if (actionName === 'stop' && !(await confirmDialog({title:'Matikan Hermes?',message:'Sesi aktif tidak akan menerima pesan baru sampai Hermes dinyalakan kembali.',confirmLabel:'Matikan',danger:true}))) return;
  if (actionName === 'shutdown' && !(await confirmDialog({title:'Shutdown Hermes?',message:'Gateway dan dashboard Hermes akan dihentikan. Autostart dimatikan; tombol Start akan mengaktifkannya lagi.',confirmLabel:'Shutdown',danger:true}))) return;
  const labels = {start:'Hermes sudah dinyalakan.', stop:'Hermes sudah dihentikan.', restart:'Hermes sudah di-restart.', shutdown:'Hermes dimatikan dan autostart dinonaktifkan.'};
  action(actionName, labels[actionName]);
}));
$('load-logs').addEventListener('click', () => action('logs', 'Log diperbarui.'));
$('refresh-models').addEventListener('click', async () => {
  try { const result = await api('/api/action', {action:'refresh-models'}); if (current) { current.router=result.data; renderModels(result.data.models || []); $('model-connection-copy').textContent=result.data.ok?`${result.data.count} pilihan (model + combo) dari ${result.data.url}.`:result.data.error; } if (!result.ok) notice(result.data.error || '9Router belum tersambung.', 'error'); else notice(`${result.data.count} model dan combo 9Router ditemukan.`); }
  catch (error) { notice(error.message, 'error'); }
});
$('test-router').addEventListener('click', () => $('refresh-models').click());
$('pick-model').addEventListener('click', async () => {
  if ($('provider').value === 'custom') { $('refresh-models').click(); return; }
  $('pick-model').disabled = true;
  try {
    const result = await api('/api/action', {action:'refresh-nous-models'});
    if (current) current.nous_models = result.models || [];
    renderModelOptions(result.models || [], $('model-id').value);
    $('model-help').textContent = `${(result.models || []).filter((model) => model.tier === 'free').length} model gratis terverifikasi. ${result.warning ? 'Sebagian sumber gagal dimuat; cache Hermes dipakai.' : 'Katalog Nous terbaru dimuat.'}`;
    notice(result.message || 'Katalog Nous dimuat.', result.warning ? '' : 'success');
  } catch (error) { notice(error.message, 'error'); }
  finally { $('pick-model').disabled = false; }
});
$('toggle-router-key').addEventListener('click', () => {
  const input = $('router-api-key');
  const visible = input.type === 'password';
  input.type = visible ? 'text' : 'password';
  $('toggle-router-key').textContent = visible ? 'Sembunyikan' : 'Tampilkan';
  $('toggle-router-key').setAttribute('aria-label', visible ? 'Sembunyikan API key' : 'Tampilkan API key');
  $('toggle-router-key').setAttribute('aria-pressed', String(visible));
});
$('save-model').addEventListener('click', async () => {
  $('new-chat-fallback').hidden = true;
  const provider = $('provider').value;
  const modelId = $('model-id').value;
  if (!modelId) { notice('Pilih model dulu.', 'error'); return; }
  const selected = provider === 'nous' ? (current?.nous_models || []).find((model) => model.id === modelId) : null;
  if (provider === 'nous' && selected?.tier !== 'free' && !(await confirmDialog({
    title: selected?.tier === 'paid' ? 'Model ini berbayar' : 'Status gratis belum pasti',
    message: selected?.tier === 'paid'
      ? `${modelId} mempunyai harga di katalog Nous Portal. Pemakaian dapat mengurangi kredit akunmu.`
      : `Harga ${modelId} belum terverifikasi. Cek Nous Portal sebelum memakai jika ingin tetap gratis.`,
    confirmLabel:'Tetap pilih model', danger:true
  }))) return;
  const changing = provider !== current?.model?.provider || modelId !== current?.model?.default ||
    (provider === 'custom' && $('base-url').value.trim().replace(/\/$/, '') !== current?.model?.base_url);
  const chatTab = changing && current?.hermes?.running ? window.open('about:blank', '_blank') : null;
  $('save-model').disabled = true;
  try {
    const result = await api('/api/action', {action:'save-model', provider, default:modelId,
      base_url:$('base-url').value, api_key:provider === 'custom' ? $('router-api-key').value : ''});
    if (!result.ok) throw new Error(result.error || 'Gagal mengganti model.');
    notice(result.message || 'Model disimpan.', 'success');
    $('router-api-key').value = '';
    $('router-api-key').type = 'password';
    $('toggle-router-key').textContent = 'Tampilkan';
    $('toggle-router-key').setAttribute('aria-label', 'Tampilkan API key');
    $('toggle-router-key').setAttribute('aria-pressed', 'false');
    if (result.model_changed) {
      if (!result.chat_ready) {
        if (chatTab) chatTab.close();
        $('new-chat-fallback').hidden = false;
        notice('Dashboard Hermes belum siap. Buka chat baru setelah Hermes aktif.', 'error');
      } else if (chatTab) chatTab.location.replace('http://127.0.0.1:9119/chat');
      else { $('new-chat-fallback').hidden = false; notice('Popup chat diblokir. Klik “Buka chat baru Hermes”.', 'error'); }
    } else if (chatTab) chatTab.close();
    await refresh();
  } catch (error) { if (chatTab) chatTab.close(); notice(error.message, 'error'); }
  finally { $('save-model').disabled = false; }
});
document.querySelectorAll('[data-save-service]').forEach((button) => button.addEventListener('click', async () => {
  const name = button.dataset.saveService;
  if (!(await confirmDialog({title:`Simpan unit ${name}?`, message:'HERMIN membuat backup, memvalidasi unit systemd, lalu memuat ulang daemon.', confirmLabel:'Simpan unit'}))) return;
  await save({action:'save-service', name, text:$(`service-${name}-editor`).value}, 'Unit tersimpan.', `service-${name}-editor`);
}));
document.querySelectorAll('[data-router-action]').forEach((button) => button.addEventListener('click', async () => {
  const verb = button.dataset.routerAction;
  if (verb === 'stop' && !(await confirmDialog({title:'Hentikan 9Router?', message:'Hermes dan OpenCode tidak dapat memakai endpoint 9Router sampai dinyalakan kembali.', confirmLabel:'Hentikan', danger:true}))) return;
  if (verb === 'shutdown' && !(await confirmDialog({title:'Shutdown 9Router?', message:'Layanan akan dihentikan dan autostart saat login dinonaktifkan. Tombol Start akan mengaktifkannya lagi.', confirmLabel:'Shutdown', danger:true}))) return;
  try {
    const result = await api('/api/action', {action:`router-${verb}`});
    if (verb === 'logs') { $('router-service-logs').textContent = result.stdout || '(jurnal kosong)'; $('router-service-logs').hidden = false; }
    else { notice(`9Router: ${verb} berhasil.`, 'success'); await refresh(); }
  } catch (error) { notice(error.message, 'error'); }
}));
document.querySelectorAll('[data-save-text]').forEach((button) => button.addEventListener('click', async () => {
  const names = {soul:'soul-editor', memory:'memory-editor', user_memory:'user-memory-editor'};
  const name = button.dataset.saveText;
  button.disabled = true;
  try { await save({action:'save-text', name, text:$(names[name]).value}, 'File disimpan.', names[name]); }
  finally { button.disabled = false; }
}));
$('reveal-env').addEventListener('click', async () => {
  if (!(await confirmDialog({title:'Buka editor rahasia?',message:'Nilai environment sensitif akan tampil di layar ini.',confirmLabel:'Buka editor'}))) return;
  try {
    const response = await fetch('/api/env/full'); const data = await response.json();
    $('env-editor').value = data.text; $('env-editor-panel').hidden = false;
    $('reveal-env').hidden = true; $('hide-env').hidden = false; isEnvOpen = true;
  } catch (error) { notice(`Tidak bisa membuka .env: ${error.message}`, 'error'); }
});
$('hide-env').addEventListener('click', () => {
  $('env-editor').value = ''; delete $('env-editor').dataset.dirty; $('env-editor-panel').hidden = true;
  $('reveal-env').hidden = false; $('hide-env').hidden = true; isEnvOpen = false;
});
$('save-env').addEventListener('click', async () => {
  if (!isEnvOpen) return;
  if (!(await confirmDialog({title:'Simpan environment?',message:'File akan disimpan dengan izin akses ketat dan nilainya tidak dimasukkan ke log.',confirmLabel:'Simpan'}))) return;
  const wasOpen = isEnvOpen;
  try {
    const result = await api('/api/action', {action:'save-env', text:$('env-editor').value});
    if (!result.ok) throw new Error(result.error || 'Gagal menyimpan .env');
    notice(result.message, 'success');
    $('env-editor').value = ''; delete $('env-editor').dataset.dirty; $('env-editor-panel').hidden = true;
    $('reveal-env').hidden = false; $('hide-env').hidden = true; isEnvOpen = false;
    await refresh();
  } catch (error) { notice(error.message, 'error'); if (wasOpen) $('env-editor-panel').hidden = false; }
});

document.querySelectorAll('textarea').forEach((editor) => editor.addEventListener('input', () => {
  editor.dataset.dirty = 'true';
  updateEditorStatus(editor);
}));
window.addEventListener('beforeunload', (event) => {
  if (document.querySelector('textarea[data-dirty]')) { event.preventDefault(); event.returnValue = ''; }
});
document.querySelectorAll('[data-document]').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('[data-document]').forEach((item) => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      $(`document-${item.dataset.document}`).hidden = !selected;
    });
  });
  tab.addEventListener('keydown', (event) => {
    const tabs = [...document.querySelectorAll('[data-document]')];
    let index = tabs.indexOf(tab);
    if (event.key === 'ArrowRight') index = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') index = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home') index = 0;
    else if (event.key === 'End') index = tabs.length - 1;
    else return;
    event.preventDefault(); tabs[index].click(); tabs[index].focus();
  });
});
$('restore-privacy').addEventListener('click', async () => {
  if (document.querySelector('.memory-editor[data-dirty]')) {
    notice('Simpan perubahan Soul/memory dahulu sebelum menerapkan ulang aturan.', 'error'); return;
  }
  if (!(await confirmDialog({title:'Terapkan ulang aturan privasi?', message:'Blok aturan standar diperbarui di Soul, memory, dan profil. Konfirmasi perintah berisiko memakai mode manual; instalasi otomatis dimatikan. Buka sesi baru setelah selesai.', confirmLabel:'Terapkan aturan'}))) return;
  $('restore-privacy').disabled = true;
  try { await save({action:'restore-privacy'}, 'Aturan privasi diperbarui.'); }
  finally { $('restore-privacy').disabled = false; }
});
$('modal-confirm').addEventListener('click',()=>settleConfirm(true));
$('modal-cancel').addEventListener('click',()=>settleConfirm(false));
$('modal-close').addEventListener('click',()=>settleConfirm(false));
$('confirm-modal').addEventListener('click',(event)=>{if(event.target===$('confirm-modal'))settleConfirm(false);});
document.addEventListener('keydown',(event)=>{if(event.key==='Escape'&&!$('confirm-modal').hidden)settleConfirm(false);});
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Tab' || $('confirm-modal').hidden) return;
  const buttons = [...$('confirm-modal').querySelectorAll('button:not(:disabled)')];
  if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons.at(-1).focus(); }
  else if (!event.shiftKey && document.activeElement === buttons.at(-1)) { event.preventDefault(); buttons[0].focus(); }
});

refresh();
window.setInterval(() => {
  if (!document.hidden && $('confirm-modal').hidden && !document.querySelector('input:focus, select:focus, textarea:focus')) refresh();
}, 60_000);

$('open-opencode-web').addEventListener('click', () => {
  const frame=$('opencode-web-embed');
  if(!frame.getAttribute('src')) frame.src='/opencode-web?autostart=1';
  frame.hidden=false;
  frame.scrollIntoView({behavior:'smooth',block:'start'});
});

$('check-update').addEventListener('click', async () => {
  $('check-update').disabled = true; $('update-status').textContent = 'Memeriksa GitHub…'; $('update-command').hidden = true;
  try {
    const data = await api('/api/update');
    $('update-status').textContent = data.message;
    if (data.command) { $('update-command').textContent = data.command; $('update-command').hidden = false; }
  } catch (error) { $('update-status').textContent = `Pemeriksaan gagal: ${error.message}`; }
  finally { $('check-update').disabled = false; }
});
