(() => {
  'use strict';
  const i18n = window.RfidI18n;
  const store = window.RfidOffline;
  const $ = id => document.getElementById(id);
  const state = { device: null, session: null, renderedSessionId: null, stream: null, cameraTimer: null };
  const normalized = value => String(value || '').trim().toUpperCase();
  const value = id => $(id).value.trim();
  const show = (id, visible) => { $(id).hidden = !visible; };
  const notice = (key, kind = 'info', values = {}) => {
    const node = $('notice');
    node.className = `alert alert-${kind}`;
    node.textContent = i18n.text(key, values);
    node.hidden = false;
  };
  const explain = error => {
    if (error?.code && (window.FinishedGoodRfidCatalog?.[i18n.language] || {})[error.code]) {
      notice(error.code, 'danger');
    } else notice(navigator.onLine ? 'error.unexpected' : 'error.network', 'danger');
  };
  const api = async (operation, payload = {}, method = 'GET') => {
    if (!navigator.onLine) throw { code: 'error.network' };
    const data = { deviceId: state.device?.id, ...payload };
    const path = `/api/method/finished_good_pack_rfid_scan.api.dispatch?operation=${encodeURIComponent(operation)}`;
    const url = method === 'GET' ? `${path}&${new URLSearchParams(Object.entries(data).filter(([, v]) => v !== undefined && v !== null).map(([k, v]) => [k, Array.isArray(v) ? JSON.stringify(v) : String(v)]))}` : path;
    let response;
    try {
      response = await fetch(url, {
        method, credentials: 'same-origin', cache: 'no-store',
        headers: { Accept: 'application/json', 'Accept-Language': i18n.language,
          ...(method === 'POST' ? { 'Content-Type': 'application/json' } : {}),
          ...(window.frappe?.csrf_token ? { 'X-Frappe-CSRF-Token': window.frappe.csrf_token } : {}) },
        ...(method === 'POST' ? { body: JSON.stringify(data) } : {}),
      });
    } catch { throw { code: 'error.network' }; }
    let envelope;
    try { envelope = (await response.json()).message; } catch { throw { code: 'error.network' }; }
    if (!envelope?.success) throw { code: envelope?.errorCode || 'error.unexpected' };
    return envelope.data;
  };
  const renderNetwork = () => {
    const node = $('network-status');
    node.className = `indicator-pill ${navigator.onLine ? 'green' : 'orange'} mr-2`;
    node.textContent = i18n.text(navigator.onLine ? 'ui.online' : 'ui.offline');
  };
  const renderDeviceInfo = () => {
    const badge = $('device-status-badge');
    badge.className = `indicator-pill ${state.device ? 'green' : 'orange'}`;
    badge.textContent = i18n.text(state.device ? 'ui.device_activated' : 'ui.device_not_activated');
    $('device-name-label').textContent = state.device?.deviceName || i18n.text('ui.not_available');
    $('device-company-label').textContent = state.device?.companyName || i18n.text('ui.not_available');
  };
  const views = name => {
    for (const id of ['device-view', 'home-view', 'session-view']) show(id, id === name);
  };
  const table = (target, columns, rows) => {
    const parent = $(target);
    parent.replaceChildren();
    if (!rows.length) { const p = document.createElement('p'); p.className = 'text-muted'; p.textContent = i18n.text('ui.empty_rows'); parent.append(p); return; }
    const element = document.createElement('table'); element.className = 'table table-bordered';
    const head = document.createElement('thead'); const header = document.createElement('tr');
    for (const [label] of columns) { const th = document.createElement('th'); th.scope = 'col'; th.textContent = i18n.text(label); header.append(th); }
    head.append(header); element.append(head);
    const body = document.createElement('tbody');
    for (const row of rows) { const tr = document.createElement('tr'); for (const [, read] of columns) { const td = document.createElement('td'); const content = read(row); if (content instanceof Node) td.append(content); else td.textContent = String(content ?? ''); tr.append(td); } body.append(tr); }
    element.append(body); parent.append(element);
  };
  const scansForSession = async () => state.session ? store.scans(state.session.sessionId) : [];
  const renderSession = async () => {
    const s = state.session;
    if (!s) return;
    views('session-view');
    $('session-title').textContent = (s.bookingIds || []).join(', ') || s.sessionId;
    const local = await scansForSession();
    const scans = s.sessionStatus === 'Completed' ? (s.scannedItems || []) : local;
    const plannedItems = (s.preloadedBookings || []).flatMap(b => (b.items || []).map(item => ({ ...item, bookingId: b.bookingId })));
    const localBoxes = new Set(scans.map(scan => `${scan.bookingId}|${scan.orderNo}|${scan.doNo}|${scan.dispPackNum}`).filter(x => !x.endsWith('|'))).size;
    const metalCount = scans.filter(scan => {
      const item = plannedItems.find(x => x.bookingId === scan.bookingId && x.finishedGoodPackDetailId === scan.finishedGoodPackDetailId);
      return ['Y', 'YES', 'TRUE', '1'].includes(normalized(item?.isMetalCheck || scan.isMetalCheck));
    }).length;
    $('session-summary').textContent = `${i18n.text('ui.scan_count', { count: scans.length })} · ${i18n.text('ui.metal_checked')}: ${metalCount} · ${i18n.text('ui.box_progress', { scanned: localBoxes, planned: s.plannedBoxCount || 0 })}`;
    if (state.renderedSessionId !== s.sessionId || s.sessionStatus !== 'Active') {
      $('session-vehicle').value = s.vehiclePlateNumber || '';
      $('session-driver').value = s.driverFullName || '';
      $('session-note').value = s.note || '';
    }
    state.renderedSessionId = s.sessionId;
    const editable = s.sessionStatus === 'Active';
    for (const id of ['scan-controls', 'refresh-booking', 'rehydrate-plan', 'complete-session', 'delete-session']) show(id, editable);
    for (const id of ['session-vehicle', 'session-driver', 'session-note']) $(id).disabled = !editable;
    const warnings = s.planningWarnings || [];
    show('session-warnings', warnings.length > 0); $('session-warnings').replaceChildren(...warnings.map(w => { const p = document.createElement('p'); p.textContent = w; return p; }));
    const bookingSelect = $('booking-select');
    const selectedBooking = bookingSelect.value;
    bookingSelect.replaceChildren(...(s.bookingIds || []).map(id => { const option = document.createElement('option'); option.value = id; option.textContent = id; return option; }));
    if ((s.bookingIds || []).includes(selectedBooking)) bookingSelect.value = selectedBooking;
    const bookingRows = (s.preloadedBookings || []).flatMap(b => b.items || []);
    const scannedIds = new Set(scans.map(x => `${x.bookingId}|${x.finishedGoodPackDetailId}`));
    const po = new Map(), items = new Map(), boxes = new Map();
    for (const item of bookingRows) {
      const booking = (s.preloadedBookings || []).find(b => b.items?.includes(item));
      const bookingId = booking?.bookingId || '';
      const found = scannedIds.has(`${bookingId}|${item.finishedGoodPackDetailId}`);
      for (const [map, signature, label] of [[po, `${bookingId}|${item.orderNo}`, item.orderNo], [items, `${bookingId}|${item.itemCode}|${item.colorCode}|${item.sizeCode}`, [item.itemCode, item.colorCode, item.sizeCode].filter(Boolean).join(' / ')], [boxes, `${bookingId}|${item.doNo}|${item.dispPackNum}`, item.dispPackNum]]) {
        const row = map.get(signature) || { label, total: 0, scanned: 0 };
        row.total += 1; row.scanned += Number(found); map.set(signature, row);
      }
    }
    const progress = rows => [...rows.values()].map(row => ({ ...row, progress: `${row.scanned}/${row.total}` }));
    const columns = label => [[label, row => row.label], ['ui.scanned', row => row.progress]];
    table('po-list', columns('ui.po'), progress(po));
    table('item-list', columns('ui.items'), progress(items));
    table('box-list', columns('ui.boxes'), progress(boxes));
    const scanColumns = [['ui.scan_rfid', row => row.rfid], ['ui.po', row => row.orderNo], ['ui.boxes', row => row.dispPackNum]];
    if (editable) scanColumns.push(['ui.delete', row => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-default btn-sm'; button.textContent = i18n.text('ui.delete');
      button.onclick = async () => { await store.remove('scans', `${s.sessionId}|${normalized(row.rfid)}`); notice('success.scan_removed', 'success'); await renderSession(); };
      return button;
    }]);
    table('scan-list', scanColumns, scans);
  };
  const saveSession = async session => { state.session = session; await store.put('sessions', session); await store.put('meta', session.sessionId, 'currentSession'); await renderSession(); };
  const openSession = async sessionId => {
    try { await saveSession(await api('session', { sessionId })); }
    catch (error) {
      const cached = await store.get('sessions', sessionId);
      if (cached && cached.deviceId === state.device?.id && !navigator.onLine) await saveSession(cached);
      else explain(error);
    }
  };
  const sessionCards = (target, rows, emptyKey) => {
    const parent = $(target); parent.replaceChildren();
    if (!rows.length) { const p = document.createElement('p'); p.className = 'text-muted'; p.textContent = i18n.text(emptyKey); parent.append(p); return; }
    for (const row of rows) {
      const card = document.createElement('div'); card.className = 'border rounded p-2 mb-2';
      const title = document.createElement('div'); title.textContent = (row.bookingIds || []).join(', ') || row.sessionId;
      const meta = document.createElement('small'); meta.className = 'text-muted d-block'; meta.textContent = `${row.vehiclePlateNumber || ''} · ${row.totalScannedCount || 0}`;
      const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-default btn-sm mt-2'; button.textContent = i18n.text('ui.resume'); button.onclick = () => openSession(row.sessionId);
      card.append(title, meta, button); parent.append(card);
    }
  };
  const loadHome = async () => {
    if (!state.device) return views('device-view');
    views('home-view');
    $('device-summary').textContent = `${state.device.deviceName} · ${state.device.companyName}`;
    try {
      const [active, history] = await Promise.all([api('active'), api('history')]);
      sessionCards('active-list', active, 'ui.empty_sessions');
      sessionCards('history-list', history.items, 'ui.empty_history');
    } catch (error) {
      if (!navigator.onLine) {
        const cached = (await store.all('sessions')).filter(s => s.deviceId === state.device.id);
        sessionCards('active-list', cached.filter(s => s.sessionStatus === 'Active'), 'ui.empty_sessions');
        sessionCards('history-list', cached.filter(s => s.sessionStatus === 'Completed'), 'ui.empty_history');
      } else explain(error);
    }
  };
  const activate = async id => {
    try {
      const device = await api('device_check', { deviceId: id });
      state.device = device; await store.put('meta', device, 'device');
      $('device-id').value = device.id; renderDeviceInfo(); stopCamera(); notice('success.device_ready', 'success'); await loadHome();
    } catch (error) { explain(error); }
  };
  const start = async () => {
    const bookingIds = value('booking-ids').split(/[\n,;]+/).map(x => x.trim()).filter(Boolean);
    if (!bookingIds.length) return notice('error.bookings_required', 'danger');
    try {
      const preview = await api('preview_conflicts', { bookingIds });
      const confirmConflicts = preview.sessions.length > 0;
      if (confirmConflicts && !window.confirm(i18n.text('ui.confirm_conflict'))) return;
      const result = await api('start', { bookingIds, confirmConflicts, vehiclePlateNumber: value('vehicle'), driverFullName: value('driver') }, 'POST');
      await saveSession(result.session); notice('success.session_started', 'success');
    } catch (error) { explain(error); }
  };
  const addScan = async () => {
    if (!state.session || state.session.sessionStatus !== 'Active') return;
    const rfid = value('rfid-input'), normalizedRfid = normalized(rfid);
    const bookings = state.session.preloadedBookings || [];
    const matches = bookings.flatMap(b => (b.items || []).filter(x => normalized(x.rfid) === normalizedRfid).map(item => ({ booking: b, item })));
    if (!normalizedRfid || matches.length !== 1) return notice('error.scan_not_in_plan', 'danger');
    const scans = await scansForSession();
    if (scans.some(x => normalized(x.rfid) === normalizedRfid)) return notice('error.scan_duplicate', 'danger');
    const { booking, item } = matches[0];
    const scan = { bookingId: booking.bookingId, finishedGoodPackDetailId: item.finishedGoodPackDetailId,
      rfid: item.rfid, orderNo: item.orderNo, doNo: item.doNo, dispPackNum: item.dispPackNum, scannedAtUtc: new Date().toISOString() };
    try {
      await store.put('scans', { key: `${state.session.sessionId}|${normalizedRfid}`, sessionId: state.session.sessionId, payload: scan });
      $('rfid-input').value = ''; $('rfid-input').focus(); notice('success.scan_saved', 'success'); await renderSession();
    } catch { notice('error.offline_storage', 'danger'); }
  };
  const complete = async () => {
    if (!navigator.onLine) return notice('ui.network_required', 'warning');
    if (!window.confirm(i18n.text('ui.confirm_complete'))) return;
    try {
      const scans = await scansForSession();
      const session = await api('complete', { sessionId: state.session.sessionId, scans,
        vehiclePlateNumber: value('session-vehicle'), driverFullName: value('session-driver'), note: value('session-note') }, 'POST');
      await store.clearScans(state.session.sessionId); await saveSession(session); notice('success.session_completed', 'success');
    } catch (error) { explain(error); }
  };
  const deleteSession = async () => {
    if (!window.confirm(i18n.text('ui.confirm_delete'))) return;
    try {
      await api('delete', { sessionId: state.session.sessionId }, 'POST');
      await store.clearScans(state.session.sessionId); await store.remove('sessions', state.session.sessionId);
      await store.remove('meta', 'currentSession'); state.session = null; notice('success.session_deleted', 'success'); await loadHome();
    } catch (error) { explain(error); }
  };
  const refreshBooking = async () => {
    const bookingId = value('booking-select');
    if (!bookingId) return notice('error.plan_missing', 'danger');
    try {
      const result = await api('refresh_delta', { sessionId: state.session.sessionId, bookingId }, 'POST');
      await saveSession(result.session); notice('success.booking_refreshed', 'success');
    } catch (error) { explain(error); }
  };
  const rehydrate = async () => {
    try { const result = await api('rehydrate', { sessionId: state.session.sessionId }, 'POST'); await saveSession(result.session); notice('success.plan_restored', 'success'); }
    catch (error) { explain(error); }
  };
  const stopCamera = () => {
    if (state.cameraTimer) clearInterval(state.cameraTimer);
    state.cameraTimer = null;
    if (state.stream) state.stream.getTracks().forEach(track => track.stop());
    state.stream = null; $('qr-video').srcObject = null;
    $('camera-status').textContent = i18n.text('ui.camera_idle');
  };
  const parseDeviceId = raw => {
    try { const url = new URL(raw); return url.searchParams.get('deviceId') || url.searchParams.get('id') || raw; }
    catch { return raw; }
  };
  const scanQr = async () => {
    if (!window.isSecureContext) return notice('error.camera_secure', 'danger');
    if (!('BarcodeDetector' in window) || !navigator.mediaDevices?.getUserMedia) return notice('error.camera_unsupported', 'danger');
    try {
      const detector = new BarcodeDetector({ formats: ['qr_code'] });
      state.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      const video = $('qr-video'); video.srcObject = state.stream; await video.play();
      $('camera-status').textContent = i18n.text('ui.camera_scanning');
      state.cameraTimer = setInterval(async () => {
        if (!state.stream || video.readyState < 2) return;
        try { const codes = await detector.detect(video); if (codes.length) { const id = parseDeviceId(codes[0].rawValue); stopCamera(); $('device-id').value = id; await activate(id); } }
        catch { /* Keep the camera open for the next frame. */ }
      }, 500);
    } catch { stopCamera(); notice('error.camera_failed', 'danger'); }
  };
  const init = async () => {
    i18n.render(); $('language').value = i18n.language; renderNetwork();
    $('language').onchange = event => i18n.setLanguage(event.target.value);
    document.addEventListener('rfid:language', () => { renderNetwork(); renderDeviceInfo(); if (state.session) renderSession(); else if (state.device) loadHome(); });
    window.addEventListener('online', renderNetwork); window.addEventListener('offline', renderNetwork);
    $('activate-device').onclick = () => activate(value('device-id'));
    $('check-device').onclick = () => activate(value('device-id'));
    $('device-id').onkeydown = event => { if (event.key === 'Enter') activate(value('device-id')); };
    $('scan-qr').onclick = scanQr;
    $('change-device').onclick = async () => { stopCamera(); state.device = null; state.session = null; renderDeviceInfo(); $('device-id').value = ''; await store.remove('meta', 'device'); await store.remove('meta', 'currentSession'); views('device-view'); };
    $('start-session').onclick = start;
    $('refresh-active').onclick = loadHome; $('refresh-history').onclick = loadHome;
    $('back-home').onclick = async () => { state.session = null; await store.remove('meta', 'currentSession'); await loadHome(); };
    $('add-scan').onclick = addScan; $('rfid-input').onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); addScan(); } };
    $('complete-session').onclick = complete; $('delete-session').onclick = deleteSession;
    $('refresh-booking').onclick = refreshBooking; $('rehydrate-plan').onclick = rehydrate;
    try {
      state.device = await store.get('meta', 'device');
      renderDeviceInfo();
      if (state.device) {
        if (navigator.onLine) state.device = await api('device_check');
        const current = await store.get('meta', 'currentSession');
        if (current) await openSession(current); else await loadHome();
      } else views('device-view');
    } catch (error) { state.device = null; views('device-view'); explain(error); }
    if ('serviceWorker' in navigator && window.isSecureContext) {
      navigator.serviceWorker.register('/finished-good-pack-rfid-scan-sw.js').then(() => navigator.serviceWorker.ready).then(registration => {
        const assets = [...document.querySelectorAll('link[rel="stylesheet"]')].map(link => link.href);
        registration.active?.postMessage({ type: 'CACHE_SHELL', assets });
      }).catch(() => {});
    }
  };
  document.addEventListener('DOMContentLoaded', init);
})();
