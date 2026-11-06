(() => {
  let items = [], app = '', busy = false, loaded = false, stale = false;
  const expanded = new Set();
  const states = {available:'Tersedia', paused:'Dipause', running:'Berjalan', stopped:'Berhenti', unknown:'Belum diketahui', error:'Perlu dicek'};
  const labels = {start:'Aktifkan', pause:'Pause', restart:'Muat ulang', delete:'Hapus skill', open:'Buka folder'};
  const group = item => ['error','unknown','stopped'].includes(item.status) ? 'attention' : item.paused ? 'paused' : 'ready';
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(text, handler, className = 'button') {
    const node = element('button', text, className);
    node.type = 'button'; node.addEventListener('click', handler); return node;
  }
  function render() {
    const query = $('skills-search').value.trim().toLocaleLowerCase();
    const status = $('skills-status').value;
    const visible = items.filter(item => (!app || item.apps.includes(app)) && (!status || group(item) === status) && `${item.name} ${item.description} ${item.path}`.toLocaleLowerCase().includes(query));
    $('skills-total').textContent = loaded ? items.length : '—';
    ['ready','paused','attention'].forEach(key => { $(`skills-${key}`).textContent = loaded ? items.filter(item => group(item) === key).length : '—'; });
    document.querySelectorAll('[data-skill-app]').forEach(tab => {
      tab.setAttribute('aria-pressed', String(tab.dataset.skillApp === app));
      tab.querySelector('span').textContent = loaded ? items.filter(item => !tab.dataset.skillApp || item.apps.includes(tab.dataset.skillApp)).length : '—';
    });
    $('skills-summary').textContent = loaded ? `${visible.length} dari ${items.length} entri${app ? ` · ${app}` : ''}` : busy ? 'Memeriksa pustaka…' : 'Daftar belum tersedia';
    const focused = document.activeElement?.dataset.skillFocus;
    const list = $('skills-list'); list.replaceChildren();
    if (!visible.length) {
      const empty = element('div', '', 'skill-empty');
      empty.append(element('span', busy ? '…' : '∅', 'skill-empty-mark'), element('h3', busy && !loaded ? 'Sedang membaca skill' : !loaded ? 'Daftar belum bisa dimuat' : items.length ? 'Tidak ada skill yang cocok' : 'Belum ada skill yang terdeteksi'));
      empty.append(element('p', busy && !loaded ? 'Memeriksa file lokal dan status 9Router.' : !loaded ? 'Coba perbarui daftar. Detail kesalahan ada di atas.' : items.length ? 'Coba kata lain atau kosongkan filter untuk melihat semua skill.' : 'Pasang skill melalui agent, lalu perbarui daftar ini.'));
      if (app || query || status) empty.append(button('Reset filter', () => { app = ''; $('skills-search').value = ''; $('skills-status').value = ''; render(); $('skills-search').focus(); }));
      list.append(empty);
    }
    visible.forEach(item => {
      const row = element('details', '', `skill-row state-${group(item)}`); row.open = expanded.has(item.id);
      row.addEventListener('toggle', () => { if (row.isConnected) { if (row.open) expanded.add(item.id); else expanded.delete(item.id); } });
      const summary = element('summary', '', 'skill-summary'); summary.dataset.skillFocus = item.id;
      const mark = element('span', item.kind === 'Proses' ? '↻' : item.kind === 'Instruksi' ? '/' : '+', 'skill-mark'); mark.setAttribute('aria-hidden', 'true');
      const title = element('span', '', 'skill-title');
      title.append(element('span', item.name, 'skill-name'), element('span', item.description || 'Deskripsi belum tersedia.', 'skill-preview'));
      const meta = element('span', '', 'skill-row-meta');
      meta.append(element('span', item.apps.join(' + '), 'skill-app-label'), element('span', states[item.status] || item.status, `skill-state ${item.status}`));
      const chevron = element('span', '+', 'skill-expand'); chevron.setAttribute('aria-hidden', 'true');
      summary.append(mark, title, meta, chevron);
      const detail = element('div', '', 'skill-detail');
      const info = element('div', '', 'skill-info');
      info.append(element('p', item.description || 'Belum ada deskripsi di file skill.', 'skill-description'));
      const facts = element('dl', '', 'skill-facts');
      [['Jenis', item.kind], ['Mode', item.level], ['File diperbarui', item.modified && new Date(item.modified * 1000).toLocaleString('id-ID')]].filter(([,value]) => value).forEach(([label,value]) => {
        const pair = element('div'); pair.append(element('dt', label), element('dd', value)); facts.append(pair);
      });
      info.append(facts);
      if (item.error) info.append(element('p', item.error, 'skill-error'));
      const location = element('div', '', 'skill-location');
      location.append(element('span', 'Lokasi di komputer HERMIN', 'skill-location-label'), element('code', item.path, 'skill-path'));
      const locationActions = element('div', '', 'skill-location-actions');
      const open = button('Buka folder ↗', () => act(item, 'open')); open.disabled = busy; open.dataset.skillFocus = `${item.id}:open`;
      locationActions.append(open, button('Salin lokasi', async () => {
        try { await navigator.clipboard.writeText(item.path); notice('Lokasi disalin.'); }
        catch { notice('Lokasi belum tersalin. Pilih dan salin teks lokasi di atas.', 'error'); }
      }));
      location.append(locationActions);
      const controls = element('div', '', 'skill-controls');
      const hint = item.kind === 'Instruksi' ? 'Buka sesi baru setelah mengaktifkan atau mem-pause skill.' : item.kind === 'Proses' ? 'Pause melewati kompresi. Proses Headroom tetap hidup.' : 'Perubahan berlaku pada permintaan model berikutnya.';
      const actions = element('div', '', 'skill-actions');
      [item.paused ? 'start' : 'pause', 'restart', 'delete'].forEach(operation => {
        const text = operation === 'restart' && item.kind === 'Proses' ? 'Restart proses' : labels[operation];
        const b = button(text, () => act(item, operation), `button ${operation === 'start' ? 'primary' : operation === 'delete' ? 'danger-outline' : ''}`);
        b.disabled = busy || stale || !item.writable || (operation === 'delete' && !item.deletable);
        b.dataset.skillFocus = `${item.id}:${operation}`;
        b.setAttribute('aria-label', `${text}: ${item.name}`); actions.append(b);
      });
      const note = element('div', '', 'skill-control-note'); note.append(element('p', hint));
      if (!item.writable) note.append(element('small', 'Hanya baca. Lokasi ini tidak dapat diubah dari HERMIN.'));
      else if (!item.deletable) note.append(element('small', 'Fitur bawaan 9Router dapat dipause, tetapi tidak dihapus.'));
      controls.append(note, actions); detail.append(info, location, controls); row.append(summary, detail); list.append(row);
    });
    if (focused) [...list.querySelectorAll('[data-skill-focus]')].find(node => node.dataset.skillFocus === focused && !node.disabled)?.focus({preventScroll:true});
  }
  async function act(item, operation) {
    if (busy || (stale && operation !== 'open')) return;
    if (operation !== 'open') {
      let message;
      if (operation === 'delete') message = `${item.name} akan dipindahkan ke backup dan tidak dimuat di sesi baru. Percakapan lama masih bisa menyimpan instruksinya.`;
      else if (item.kind === 'Proses') message = operation === 'pause' ? 'Permintaan berikutnya akan melewati Headroom. Proses kompresinya tetap hidup.' : 'Headroom akan dijalankan atau direstart, lalu kompresi diaktifkan di 9Router.';
      else if (item.kind === 'Instruksi') message = operation === 'restart' ? `Periksa ulang file ${item.name}. Proses agent tidak direstart. Buka sesi baru untuk memakai instruksi terbaru.` : `${item.name} akan ${operation === 'pause' ? 'dipause' : 'diaktifkan'} untuk sesi baru. Perubahan pada folder bersama juga berlaku untuk agent lain yang membacanya.`;
      else message = operation === 'restart' ? `Baca ulang pengaturan ${item.name}. Status aktif atau pause tetap sama.` : `${item.name} akan ${operation === 'pause' ? 'dipause' : 'diaktifkan'} pada permintaan model berikutnya.`;
      if (!await confirmDialog({title: `${operation === 'restart' && item.kind === 'Proses' ? 'Restart proses' : labels[operation]}?`, message, confirmLabel: operation === 'restart' && item.kind === 'Proses' ? 'Restart proses' : labels[operation], danger:operation === 'delete'})) return;
    }
    const focusKey = `${item.id}:${operation}`;
    busy = true; $('skills-refresh').disabled = true; render();
    try { notice((await api('/api/action', {action:'skill-control', id:item.id, operation})).message); }
    catch (error) { notice(error.message, 'error'); }
    finally {
      busy = false; await load();
      const target = [...$('skills-list').querySelectorAll('[data-skill-focus]')].find(node => node.dataset.skillFocus === focusKey && !node.disabled) || [...$('skills-list').querySelectorAll('summary')].find(node => node.dataset.skillFocus === item.id);
      (target || $('skills-refresh')).focus({preventScroll:true});
    }
  }
  async function load() {
    if (busy) return;
    busy = true; $('skills-refresh').disabled = true; $('skills-list').setAttribute('aria-busy', 'true');
    $('skills-warning').hidden = true; $('skills-checked').textContent = 'Memeriksa…'; render();
    try {
      const result = await api('/api/skills'); csrf = result.csrf;
      items = result.items; loaded = true; stale = false;
      $('skills-scope').textContent = result.scope;
      $('skills-warning').textContent = result.warnings.join(' '); $('skills-warning').hidden = !result.warnings.length;
      $('skills-checked').textContent = `Dicek ${new Date().toLocaleTimeString('id-ID', {hour:'2-digit', minute:'2-digit'})}`;
    } catch (error) {
      stale = true; $('skills-warning').hidden = false;
      $('skills-warning').textContent = `Daftar belum diperbarui: ${error.message}. Coba lagi sebelum mengubah skill.`;
      $('skills-checked').textContent = 'Pemeriksaan gagal';
    } finally { busy = false; render(); $('skills-refresh').disabled = false; $('skills-list').setAttribute('aria-busy','false'); }
  }
  document.querySelectorAll('[data-skill-app]').forEach(tab => tab.addEventListener('click', () => { app = tab.dataset.skillApp; render(); }));
  $('skills-status').addEventListener('change', render);
  $('skills-search').addEventListener('input', render);
  $('skills-refresh').addEventListener('click', load);
  window.loadSkills = load;
})();
