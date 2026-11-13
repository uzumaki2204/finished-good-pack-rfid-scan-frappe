(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const t = (key, values) => window.RfidI18n.text(key, values);
  const MAX_BYTES = 20 * 1024 * 1024;
  let api, context, scope, cursor = null, loading = false, busy = false, queue = [], pending = Promise.resolve();
  const element = (tag, text = '', className = '') => {
    const result = document.createElement(tag); result.textContent = text; result.className = className; return result;
  };
  const status = key => { $('photo-status').textContent = key ? t(key) : ''; };
  const errorText = error => {
    const catalog = window.FinishedGoodRfidCatalog?.[window.RfidI18n.language] || {};
    return catalog[error?.code] ? t(error.code) : t('ui.photo_failed');
  };
  const uuid = () => {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  };
  const photoUrl = (id, thumbnail = false) => `/api/method/finished_good_pack_rfid_scan.api.photo_content?${new URLSearchParams({
    deviceId: scope.deviceId, sessionId: scope.sessionId, photoId: id, thumbnail: thumbnail ? '1' : '0',
  })}`;
  const renderQueue = () => {
    $('photo-queue').replaceChildren();
    for (const item of queue) {
      const row = element('div', '', 'rfid-photo-upload');
      row.append(element('strong', item.file.name));
      const progress = document.createElement('progress'); progress.max = 100; progress.value = item.progress;
      progress.setAttribute('aria-label', item.file.name); row.append(progress);
      row.append(element('small', item.error || (item.state === 'saved' ? t('ui.photo_saved') : t('ui.photo_uploading'))));
      if (item.state === 'failed') {
        const retry = element('button', t('ui.photo_retry'), 'btn btn-default'); retry.type = 'button'; retry.disabled = busy;
        retry.onclick = () => { item.state = 'waiting'; item.error = ''; runQueue(); };
        const remove = element('button', t('ui.photo_remove'), 'btn btn-default'); remove.type = 'button'; remove.disabled = busy;
        remove.onclick = () => { queue = queue.filter(row => row !== item); renderQueue(); };
        row.append(retry, remove);
      }
      $('photo-queue').append(row);
    }
    $('choose-photos').disabled = busy; $('take-photo').disabled = busy;
    $('close-photos').disabled = busy;
  };
  const upload = item => new Promise((resolve, reject) => {
    if (!navigator.onLine) { reject({ code: 'ui.photo_network' }); return; }
    const form = new FormData();
    form.append('deviceId', scope.deviceId); form.append('sessionId', scope.sessionId);
    form.append('requestId', item.requestId); form.append('file', item.file);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/method/finished_good_pack_rfid_scan.api.upload_photo');
    xhr.withCredentials = true; xhr.timeout = 180000;
    if (window.frappe?.csrf_token) xhr.setRequestHeader('X-Frappe-CSRF-Token', window.frappe.csrf_token);
    xhr.setRequestHeader('Accept-Language', window.RfidI18n.language);
    xhr.upload.onprogress = event => { if (event.lengthComputable) { item.progress = Math.round(event.loaded * 100 / event.total); renderQueue(); } };
    xhr.onload = () => {
      let result;
      try { result = JSON.parse(xhr.responseText).message; } catch { /* Gateway failures may return HTML. */ }
      if (xhr.status >= 200 && xhr.status < 300 && result?.success) resolve(result.data);
      else reject({ code: result?.errorCode || (xhr.status === 413 ? 'error.photo_size' : 'ui.photo_failed') });
    };
    xhr.onerror = xhr.ontimeout = () => reject({ code: navigator.onLine ? 'ui.photo_failed' : 'ui.photo_network' });
    xhr.send(form);
  });
  const runQueue = () => {
    if (busy) return;
    busy = true; renderQueue();
    pending = (async () => {
      for (const item of queue.filter(row => row.state === 'waiting')) {
        try {
          item.state = 'uploading'; renderQueue();
          if (!item.file.size || item.file.size > MAX_BYTES) throw { code: 'error.photo_size' };
          await upload(item); item.state = 'saved'; item.progress = 100;
        } catch (error) { item.state = 'failed'; item.error = errorText(error); }
        renderQueue();
      }
    })().finally(async () => {
      queue = queue.filter(row => row.state !== 'saved'); busy = false; renderQueue();
      await loadPhotos(true);
    });
  };
  const addFiles = files => {
    if (!navigator.onLine) { status('ui.photo_network'); return; }
    for (const file of files) queue.push({ file, requestId: uuid(), progress: 0, state: 'waiting', error: '' });
    runQueue();
  };
  const loadPhotos = async (reset = false) => {
    if (loading || !scope) return;
    if (!navigator.onLine) { status('ui.photo_network'); return; }
    loading = true; $('more-photos').disabled = true; $('reload-photos').disabled = true;
    const requestedScope = scope;
    try {
      const result = await api('photos', { sessionId: scope.sessionId, before: reset ? undefined : cursor });
      if (requestedScope !== scope) return;
      if (reset) $('photo-grid').replaceChildren();
      for (const photo of result.items) {
        const card = element('article', '', 'rfid-photo-card');
        const open = element('button', '', 'rfid-photo-open'); open.type = 'button'; open.setAttribute('aria-label', photo.fileName);
        const image = document.createElement('img'); image.src = photoUrl(photo.id, true); image.alt = photo.fileName; image.loading = 'lazy';
        image.onerror = () => { status('ui.photo_failed'); };
        open.append(image);
        open.onclick = () => { $('photo-full').src = photoUrl(photo.id); $('photo-full').alt = photo.fileName; $('photo-viewer').showModal(); };
        const remove = element('button', t('ui.photo_delete'), 'btn btn-default'); remove.type = 'button';
        remove.onclick = async () => {
          if (!navigator.onLine) { status('ui.photo_network'); return; }
          if (!window.confirm(t('ui.photo_confirm_delete'))) return;
          remove.disabled = true;
          try { await api('delete_photo', { sessionId: requestedScope.sessionId, photoId: photo.id }, 'POST'); card.remove(); }
          catch (error) { $('photo-status').textContent = errorText(error); remove.disabled = false; }
        };
        card.append(open, element('small', `${photo.width} × ${photo.height} · ${Math.ceil(photo.size / 1024)} KB`));
        if (result.canDelete) card.append(remove);
        $('photo-grid').append(card);
      }
      cursor = result.nextCursor; $('more-photos').hidden = !cursor;
      status($('photo-grid').children.length ? '' : 'ui.photo_empty');
    } catch (error) { $('photo-status').textContent = errorText(error); }
    finally { loading = false; $('more-photos').disabled = false; $('reload-photos').disabled = false; }
  };
  const close = () => {
    if (busy || loading) { status('ui.photo_busy'); return; }
    if (queue.length && !window.confirm(t('ui.photo_leave'))) return;
    queue = []; renderQueue(); $('photo-dialog').close();
  };
  const open = async (selected = null) => {
    const current = selected?.sessionId ? selected : context();
    if (!current.sessionId) return;
    scope = current; cursor = null; queue = []; $('photo-grid').replaceChildren(); renderQueue();
    $('photo-dialog').showModal(); await loadPhotos(true);
  };
  window.RfidPhotos = {
    init(options) {
      ({ api, context } = options);
      const browse = element('button', 'Hình ảnh các phiên cùng công ty', 'btn btn-default');
      browse.type = 'button'; $('home-view').prepend(browse);
      const picker = element('dialog', '', 'rfid-photo-dialog');
      picker.style.cssText = 'width:min(720px,95vw);max-height:85vh;overflow:auto;padding:20px';
      const title = element('h3', 'Hình ảnh các phiên cùng công ty');
      const list = element('div'), footer = element('div');
      const previous = element('button','Trang trước','btn btn-default'), next = element('button','Trang sau','btn btn-default'), closePicker = element('button','Đóng','btn btn-default');
      let page = 1;
      const loadSessions = async () => {
        previous.disabled = next.disabled = true; list.textContent = 'Đang tải…';
        try {
          const result = await api('photo_sessions', {page}); list.replaceChildren();
          if (!result.items.length) list.textContent = 'Chưa có phiên.';
          for (const row of result.items) {
            let bookings; try {bookings=JSON.parse(row.booking_ids_json || '[]').join(', ');} catch {bookings=row.name;}
            const button = element('button', `${bookings || row.name} · ${row.status === 'Active' ? 'Đang scan' : 'Đã hoàn thành'} · ${row.device} · ${row.session_started_at}`, 'btn btn-default');
            button.type='button'; button.style.cssText='display:block;width:100%;text-align:left;margin:8px 0;white-space:normal';
            button.onclick = () => open({...context(),sessionId:row.name}); list.append(button);
          }
          previous.disabled = page <= 1; next.disabled = page*24 >= result.total;
        } catch(error) {list.textContent=errorText(error);}
      };
      previous.onclick=()=>{page--;void loadSessions();}; next.onclick=()=>{page++;void loadSessions();};
      closePicker.onclick=()=>picker.close(); footer.append(previous,next,closePicker); picker.append(title,list,footer); document.body.append(picker);
      browse.onclick=()=>{page=1;picker.showModal();void loadSessions();};
      $('completion-photos').onclick = open; $('session-photos').onclick = open;
      $('choose-photos').onclick = () => { if (navigator.onLine) $('photo-files').click(); else status('ui.photo_network'); };
      $('take-photo').onclick = () => { if (navigator.onLine) $('photo-camera').click(); else status('ui.photo_network'); };
      for (const id of ['photo-files', 'photo-camera']) $(id).onchange = event => { addFiles(event.target.files); event.target.value = ''; };
      $('close-photos').onclick = close;
      $('photo-dialog').addEventListener('cancel', event => { event.preventDefault(); close(); });
      $('more-photos').onclick = () => loadPhotos(); $('reload-photos').onclick = () => loadPhotos(true);
      $('close-photo-viewer').onclick = () => $('photo-viewer').close();
      $('photo-viewer').addEventListener('close', () => $('photo-full').removeAttribute('src'));
      window.addEventListener('beforeunload', event => { if (busy || queue.length) { event.preventDefault(); event.returnValue = ''; } });
    },
    async prepareCompletion(sessionId) {
      if (scope?.sessionId !== sessionId) return true;
      await pending;
      if (queue.some(item => item.state === 'failed') && !window.confirm(t('ui.photo_skip_failed'))) return false;
      queue = []; return true;
    },
  };
})();
