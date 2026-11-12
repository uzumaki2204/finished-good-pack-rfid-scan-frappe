(() => {
  'use strict';
  const i18n = window.RfidI18n;
  const store = window.RfidOffline;
  const $ = id => document.getElementById(id);
  const state = { device: null, session: null, renderedSessionId: null, stream: null, cameraTimer: null, returnView: null,
    homeTab: 'active', bookingIds: [], scanPaused: false, refreshing: false, activeSessionTab: 'po', activeBoxFilter: 'not-scanned', boxSearch: '', sessionRows: null, completing: false, completionPending: false, completionProgress: null };
  const SCAN_COMMIT_DELAY_MS = 60;
  let scannerCommitTimer = null;
  let lastFocusedRfidKeyAt = 0;
  let focusedRfidKeyBurst = 0;
  let scanQueue = Promise.resolve();
  const SESSION_TABS = ['po', 'items', 'boxes'];
  const BOX_FILTERS = ['not-scanned', 'scanning', 'completed'];
  const COMPLETION_LOCKED_CONTROLS = ['back-home', 'device-settings'];
  const normalized = value => String(value || '').trim().toUpperCase();
  const normalizedRfid = value => String(value || '').replace(/[\u0000-\u0008\u000A-\u001F\u007F-\u009F]/g, '').trim().slice(0, 200).toUpperCase();
  const formatCount = count => Number(count || 0).toLocaleString(i18n.language === 'vi' ? 'vi-VN' : 'en-US');
  const node = (tag, className = '', label = '') => { const element = document.createElement(tag); element.className = className; element.textContent = label; return element; };
  const value = id => $(id).value.trim();
  const show = (id, visible) => { const element = $(id); if (element) element.hidden = !visible; };
  const renderCompletionProgress = () => {
    const status = $('completion-upload-status');
    if (!status) return;
    const progress = state.completionProgress;
    if (!progress) { status.hidden = true; status.textContent = ''; return; }
    const messages = { uploading: 'ui.uploading_records', complete: 'ui.uploaded_records', failed: 'ui.upload_failed' };
    const styles = { uploading: 'info', complete: 'success', failed: 'danger' };
    status.className = `alert alert-${styles[progress.phase]} mb-3`;
    status.textContent = i18n.text(messages[progress.phase], {
      uploaded: formatCount(progress.uploaded), total: formatCount(progress.total),
    });
    status.hidden = false;
  };
  const lockCompletionNavigation = locked => { for (const id of COMPLETION_LOCKED_CONTROLS) $(id).disabled = locked; };
  const expandPageShell = () => $('rfid-app')?.closest('body > div')?.classList.add('w-100');
  const notice = (key, kind = 'info', values = {}) => {
    const node = $('notice');
    node.className = `alert alert-${kind}`;
    node.textContent = i18n.text(key, values);
    node.hidden = false;
  };
  const clearNotice = () => { $('notice').hidden = true; $('notice').textContent = ''; };
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
    const key = navigator.onLine ? 'ui.online' : 'ui.offline';
    const label = i18n.text(key);
    node.className = `${navigator.onLine ? 'text-success' : 'text-danger'} mr-2`;
    node.setAttribute('aria-label', label);
    node.title = label;
    $('network-status-label').textContent = label;
  };
  const renderDeviceInfo = () => {
    const badge = $('device-status-badge');
    badge.className = `indicator-pill ${state.device ? 'green' : 'orange'}`;
    badge.textContent = i18n.text(state.device ? 'ui.device_activated' : 'ui.device_not_activated');
    $('return-to-app').hidden = !state.device;
    $('device-name-label').textContent = state.device?.deviceName || i18n.text('ui.not_available');
    $('device-company-label').textContent = state.device?.companyName || i18n.text('ui.not_available');
  };
  const views = name => {
    $('rfid-app').dataset.view = name;
    for (const id of ['device-view', 'home-view', 'session-view']) show(id, id === name);
    show('back-home', name === 'session-view');
    $('screen-title').textContent = i18n.text(name === 'session-view' ? 'ui.scan_session' : name === 'device-view' ? 'ui.device_info' : 'ui.title');
    show('session-booking', name === 'session-view');
  };
  const table = (target, columns, rows, emptyKey = 'ui.empty_rows', tableClass = 'table table-bordered') => {
    const parent = $(target);
    parent.replaceChildren();
    if (!rows.length) { const p = document.createElement('p'); p.className = 'text-muted'; p.textContent = i18n.text(emptyKey); parent.append(p); return; }
    const element = document.createElement('table'); element.className = tableClass;
    const head = document.createElement('thead'); const header = document.createElement('tr');
    for (const [label] of columns) { const th = document.createElement('th'); th.scope = 'col'; th.textContent = i18n.text(label); header.append(th); }
    head.append(header); element.append(head);
    const body = document.createElement('tbody');
    for (const row of rows) { const tr = document.createElement('tr'); for (const [, read] of columns) { const td = document.createElement('td'); const content = read(row); if (content instanceof Node) td.append(content); else td.textContent = String(content ?? ''); tr.append(td); } body.append(tr); }
    element.append(body); parent.append(element);
  };
  const scansForSession = async () => state.session ? store.scans(state.session.sessionId) : [];
  const boxStatus = row => row.scanned === 0 ? 'not-scanned' : row.scanned < row.total ? 'scanning' : 'completed';
  const renderBoxList = () => {
    for (const button of document.querySelectorAll('[data-box-filter]')) {
      const active = button.dataset.boxFilter === state.activeBoxFilter;
      button.classList.toggle('btn-primary', active);
      button.classList.toggle('btn-default', !active);
      button.setAttribute('aria-pressed', String(active));
    }
    const rows = (state.sessionRows?.boxes || []).filter(row => boxStatus(row) === state.activeBoxFilter
      && (!state.boxScope || (row.bookingId === state.boxScope.bookingId && row.orderNo === state.boxScope.orderNo))
      && String(row.label || '').toLocaleLowerCase().includes(state.boxSearch));
    table('box-list', [['ui.boxes', row => row.label || i18n.text('ui.not_available')], ['ui.scanned', row => row.progress]], rows);
  };
  const itemProgress = row => `${formatCount(row.scanned)}/${formatCount(row.total)}`;
  const bookingTargetBoxes = booking => Math.max(
    Number(booking.plannedBoxCount || 0), Number(booking.headerPlannedCartonCount || 0), Number(booking.headerActualCartonCount || 0));
  const closeItemDetail = () => {
    const modal = $('item-detail-modal');
    if (modal.hidden) return;
    modal.hidden = true; modal.classList.remove('show', 'd-block'); modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
    $('rfid-app').firstElementChild.inert = false;
    document.getElementById('item-detail-backdrop')?.remove();
    const trigger = state.itemDetailTrigger; state.itemDetailTrigger = null;
    if (trigger?.isConnected) trigger.focus();
  };
  const renderItemDetail = row => {
    const body = $('item-detail-body'); body.replaceChildren();
    const summary = node('div', 'row mb-3');
    const scanned = node('div', 'col-6'); scanned.append(node('div', 'border rounded p-2 h-100 font-weight-bold', itemProgress(row)));
    const total = node('div', 'col-6');
    const totalBox = node('div', 'border rounded p-2 h-100');
    totalBox.append(node('small', 'text-muted d-block', i18n.text('ui.total_items')), node('strong', '', formatCount(row.total)));
    total.append(totalBox); summary.append(scanned, total); body.append(summary);
    if (row.pendingBoxes) {
      const key = row.pendingItems ? 'ui.item_pending_items' : 'ui.item_pending_boxes';
      body.append(node('p', 'alert alert-warning', i18n.text(key, {
        items: formatCount(row.pendingItems), boxes: formatCount(row.pendingBoxes),
      })));
    }
    for (const market of row.markets) {
      const section = node('section', 'border rounded p-2 mb-3');
      const heading = node('div', 'd-flex justify-content-between align-items-center mb-2');
      heading.append(node('strong', 'text-break mr-2', [market.code, market.name].filter(Boolean).join(' - ') || i18n.text('ui.not_available')),
        node('strong', 'text-nowrap', itemProgress(market)));
      section.append(heading);
      for (const variant of market.variants) {
        const card = node('div', 'border rounded p-2 mb-2');
        const top = node('div', 'd-flex justify-content-between align-items-center mb-2');
        top.append(node('small', 'text-muted', i18n.text('ui.color_size')), node('strong', 'text-nowrap', itemProgress(variant)));
        const color = node('div', 'd-flex flex-wrap');
        color.append(node('small', 'text-muted mr-2', i18n.text('ui.color')),
          node('span', 'text-break', [variant.colorCode, variant.colorName].filter(Boolean).join(' - ') || i18n.text('ui.not_available')));
        const size = node('div', 'd-flex flex-wrap');
        size.append(node('small', 'text-muted mr-2', i18n.text('ui.size')),
          node('span', 'text-break', [variant.sizeCode, variant.sizeName].filter(Boolean).join(' - ') || i18n.text('ui.not_available')));
        card.append(top, color, size);
        if (variant.qtyPerSet > 0) card.append(node('small', 'text-muted d-block mt-1', i18n.text('ui.qty_per_set', { count: formatCount(variant.qtyPerSet) })));
        section.append(card);
      }
      body.append(section);
    }
  };
  const openItemDetail = (row, trigger) => {
    state.itemDetailTrigger = trigger;
    $('item-detail-title').textContent = i18n.text('ui.item_details', { item: row.label || i18n.text('ui.not_available') });
    renderItemDetail(row);
    const modal = $('item-detail-modal');
    modal.hidden = false; modal.classList.add('show', 'd-block'); modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    const backdrop = node('div', 'modal-backdrop show'); backdrop.id = 'item-detail-backdrop';
    document.body.append(backdrop);
    $('rfid-app').firstElementChild.inert = true;
    $('close-item-detail').focus();
  };
  const renderItemList = rows => {
    const parent = $('item-list'); parent.replaceChildren();
    if (!rows.length) { parent.append(node('p', 'text-muted', i18n.text('ui.empty_rows'))); return; }
    for (const row of rows) {
      const card = node('article', 'border rounded p-2 mb-2');
      const layout = node('div', 'd-flex justify-content-between align-items-start');
      const meta = node('div', 'text-break mr-2');
      meta.append(node('strong', 'd-block', row.label || i18n.text('ui.not_available')),
        node('small', 'text-muted d-block', i18n.text('ui.item_po', { po: row.orderNo || i18n.text('ui.not_available') })),
        node('small', 'text-muted d-block', i18n.text('ui.item_booking', { booking: row.bookingId })),
        node('small', 'text-muted d-block', i18n.text('ui.item_box_variant_summary', {
          completed: formatCount(row.completedBoxes), boxes: formatCount(row.boxCount), variants: formatCount(row.variantCount),
        })));
      const actions = node('div', 'text-right');
      actions.append(node('strong', 'd-block text-nowrap', itemProgress(row)));
      const button = node('button', 'btn btn-default btn-sm mt-1', i18n.text('ui.item_detail_button'));
      button.type = 'button'; button.onclick = () => openItemDetail(row, button);
      actions.append(button); layout.append(meta, actions); card.append(layout); parent.append(card);
    }
  };
  const renderSelectedSessionTab = () => {
    const rows = state.sessionRows;
    if (!rows) return;
    if (state.activeSessionTab === 'po') {
      const parent = $('po-list'); parent.replaceChildren();
      if (!rows.po.length) parent.append(node('p', 'text-muted', i18n.text('ui.empty_rows')));
      for (const row of rows.po) {
        const card = node('article', 'rfid-po-card');
        const info = node('div', 'rfid-po-info');
        info.append(node('strong', 'd-block', row.label || i18n.text('ui.not_available')),
          node('small', 'text-muted d-block', i18n.text('ui.item_booking', { booking: row.bookingId })),
          node('small', 'text-muted d-block', i18n.text('ui.po_summary', { count: rows.items.filter(item => item.bookingId === row.bookingId && item.orderNo === row.label).length, progress: row.progress })));
        const actions = node('div', 'text-right');
        const button = node('button', 'btn btn-default btn-sm mt-1', i18n.text('ui.view_boxes'));
        button.type = 'button'; button.onclick = () => {
          state.boxScope = { bookingId: row.bookingId, orderNo: row.label };
          selectSessionTab('boxes', true);
        };
        actions.append(node('strong', 'd-block text-nowrap', row.progress), button);
        card.append(info, actions); parent.append(card);
      }
    }
    else if (state.activeSessionTab === 'items') renderItemList(rows.items);
    else if (state.activeSessionTab === 'boxes') renderBoxList();
  };
  const selectSessionTab = (name, focus = false) => {
    if (!SESSION_TABS.includes(name)) return;
    state.activeSessionTab = name;
    for (const button of document.querySelectorAll('[data-session-tab]')) {
      const active = button.dataset.sessionTab === name;
      button.classList.toggle('active', active);
      button.classList.toggle('btn-primary', active);
      button.classList.toggle('btn-default', !active);
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
      show(`panel-${button.dataset.sessionTab}`, active);
      if (active && focus) button.focus();
    }
    renderSelectedSessionTab();
  };
  const selectBoxFilter = (name, focus = false) => {
    if (!BOX_FILTERS.includes(name)) return;
    state.activeBoxFilter = name;
    renderBoxList();
    if (focus) document.querySelector(`[data-box-filter="${name}"]`).focus();
  };
  const navigateTabsWithKeyboard = (event, names, current, select) => {
    const index = names.indexOf(current);
    let next;
    if (event.key === 'ArrowRight') next = names[(index + 1) % names.length];
    else if (event.key === 'ArrowLeft') next = names[(index - 1 + names.length) % names.length];
    else if (event.key === 'Home') next = names[0];
    else if (event.key === 'End') next = names[names.length - 1];
    else return;
    event.preventDefault(); select(next, true);
  };
  const renderSession = async () => {
    const s = state.session;
    if (!s) return;
    closeItemDetail();
    if (state.renderedSessionId !== s.sessionId) {
      state.renderedSessionId = s.sessionId; state.scanPaused = false; state.boxScope = null; renderScanMode();
      state.activeSessionTab = 'po'; state.activeBoxFilter = 'not-scanned'; state.boxSearch = ''; state.completing = false; state.completionProgress = null;
      $('box-search').value = '';
    }
    views('session-view');
    $('session-booking').textContent = `Booking: ${(s.preloadedBookings || []).map(b => b.displayBookingId || b.bookingId).join(', ')}`;
    let local = [];
    let storageReady = true;
    if (s.sessionStatus !== 'Completed') {
      try { local = await scansForSession(); }
      catch { storageReady = false; }
    }
    const scans = s.sessionStatus === 'Completed' ? (s.scannedItems || []) : local;
    const plannedItems = (s.preloadedBookings || []).flatMap(b => (b.items || []).map(item => ({ ...item, bookingId: b.bookingId })));
    const plannedById = new Map(plannedItems.map(item => [`${item.bookingId}|${item.finishedGoodPackDetailId}`, item]));
    const metalCount = scans.filter(scan => {
      const item = plannedById.get(`${scan.bookingId}|${scan.finishedGoodPackDetailId}`);
      return ['Y', 'YES', 'TRUE', '1'].includes(normalized(item?.isMetalCheck || scan.isMetalCheck));
    }).length;
    const editable = s.sessionStatus === 'Active';
    if (!editable) state.completing = false;
    lockCompletionNavigation(state.refreshing || (editable && state.completing));
    show('scan-dock', !state.completing);
    show('scan-controls', editable);
    show('session-photos', !editable);
    show('refresh-session', editable);
    $('refresh-session').disabled = !editable || state.refreshing;
    $('complete-session').disabled = !editable || state.refreshing;
    show('scan-dock-spacer', !state.completing);
    show('completion-form', editable && state.completing);
    if (s.sessionStatus === 'Completed') {
      const total = Number(s.totalScannedCount ?? scans.length);
      state.completionProgress = { phase: 'complete', uploaded: total, total };
    }
    renderCompletionProgress();
    const warnings = s.planningWarnings || [];
    show('session-warnings', warnings.length > 0); $('session-warnings').replaceChildren(...warnings.map(w => { const p = document.createElement('p'); p.textContent = w; return p; }));
    const scannedIds = new Set(scans.map(x => `${x.bookingId}|${x.finishedGoodPackDetailId}`));
    const po = new Map(), items = new Map(), boxes = new Map(), poBoxKeys = new Map(), poPendingBoxes = new Map();
    for (const booking of s.preloadedBookings || []) {
      const bookingId = booking?.bookingId || '';
      for (const item of booking.items || []) {
        const found = scannedIds.has(`${bookingId}|${item.finishedGoodPackDetailId}`);
        const poKey = JSON.stringify([bookingId, item.orderNo || '']);
        const boxKey = JSON.stringify([bookingId, item.orderNo || '', item.doNo || '', item.dispPackNum || '']);
        if (!poBoxKeys.has(poKey)) poBoxKeys.set(poKey, new Set());
        poBoxKeys.get(poKey).add(boxKey);
        for (const [map, signature, label] of [[po, poKey, item.orderNo], [boxes, boxKey, item.dispPackNum]]) {
          const row = map.get(signature) || { label, bookingId, orderNo: item.orderNo, total: 0, scanned: 0 };
          row.total += 1; row.scanned += Number(found); map.set(signature, row);
        }
        const itemCode = item.sampleCode || item.itemCode || '';
        const itemKey = JSON.stringify([bookingId, item.orderNo || '', itemCode]);
        let row = items.get(itemKey);
        if (!row) {
          row = { label: itemCode, bookingId, orderNo: item.orderNo || '', total: 0, scanned: 0,
            boxKeys: new Set(), variantKeys: new Set(), markets: new Map(), qtyPerSetValues: new Set(), pendingBoxes: 0, pendingItems: 0 };
          items.set(itemKey, row);
        }
        row.total += 1; row.scanned += Number(found); row.boxKeys.add(boxKey);
        if (Number(item.qtyPerSet || 0) > 0) row.qtyPerSetValues.add(Number(item.qtyPerSet));
        const marketKey = JSON.stringify([item.marketCode || '', item.marketName || '']);
        let market = row.markets.get(marketKey);
        if (!market) {
          market = { code: item.marketCode || '', name: item.marketName || '', total: 0, scanned: 0, variants: new Map() };
          row.markets.set(marketKey, market);
        }
        market.total += 1; market.scanned += Number(found);
        const variantKey = JSON.stringify([item.colorCode || '', item.colorName || '', item.sizeCode || '', item.sizeName || '']);
        row.variantKeys.add(variantKey);
        let variant = market.variants.get(variantKey);
        if (!variant) {
          variant = { colorCode: item.colorCode || '', colorName: item.colorName || '', sizeCode: item.sizeCode || '',
            sizeName: item.sizeName || '', qtyPerSet: Number(item.qtyPerSet || 0), total: 0, scanned: 0 };
          market.variants.set(variantKey, variant);
        } else if (variant.qtyPerSet !== Number(item.qtyPerSet || 0)) variant.qtyPerSet = 0;
        variant.total += 1; variant.scanned += Number(found);
      }
    }
    const mappedBoxCounts = new Map();
    for (const signature of boxes.keys()) {
      const [bookingId] = JSON.parse(signature);
      mappedBoxCounts.set(bookingId, (mappedBoxCounts.get(bookingId) || 0) + 1);
    }
    let plannedBoxTotal = 0;
    const addPendingBoxes = (row, count) => {
      row.pendingBoxes += count;
      if (row.qtyPerSetValues.size === 1) {
        const qtyPerSet = row.qtyPerSetValues.values().next().value;
        row.pendingItems += count * qtyPerSet;
        row.total += count * qtyPerSet;
      }
    };
    for (const booking of s.preloadedBookings || []) {
      const bookingId = booking.bookingId || '';
      const mappedCount = mappedBoxCounts.get(bookingId) || 0;
      const target = Math.max(mappedCount, bookingTargetBoxes(booking));
      plannedBoxTotal += target;
      let remaining = target - mappedCount;
      const bookingItems = [...items.values()].filter(row => row.bookingId === bookingId);
      const bookingPoKeys = [...poBoxKeys.keys()].filter(signature => JSON.parse(signature)[0] === bookingId);
      for (const group of booking.unmappedBoxGroups || []) {
        if (!remaining) break;
        const count = Math.min(remaining, Math.max(0, Number(group.unmappedBoxCount || 0)));
        const matching = bookingItems.filter(row => normalized(row.orderNo) === normalized(group.orderNo)
          && (!group.sampleCode || normalized(row.label) === normalized(group.sampleCode)));
        if (count && matching.length === 1) addPendingBoxes(matching[0], count);
        const poKey = bookingPoKeys.find(signature => normalized(JSON.parse(signature)[1]) === normalized(group.orderNo));
        if (count && poKey) poPendingBoxes.set(poKey, (poPendingBoxes.get(poKey) || 0) + count);
        remaining -= count;
      }
      if (remaining && bookingItems.length === 1) addPendingBoxes(bookingItems[0], remaining);
      if (remaining && bookingPoKeys.length === 1) poPendingBoxes.set(bookingPoKeys[0], (poPendingBoxes.get(bookingPoKeys[0]) || 0) + remaining);
    }
    plannedBoxTotal = Math.max(plannedBoxTotal, Number(s.plannedBoxCount || 0));
    const completedBoxCount = [...boxes.values()].filter(row => row.total > 0 && row.scanned >= row.total).length;
    $('metric-scanned').textContent = formatCount(scans.length);
    $('metric-metal').textContent = formatCount(metalCount);
    $('metric-boxes').textContent = `${formatCount(completedBoxCount)}/${formatCount(plannedBoxTotal)}`;
    const progress = rows => [...rows.values()].map(row => ({ ...row, progress: `${row.scanned}/${row.total}` }));
    const poRows = [...po.entries()].map(([signature, row]) => {
      const boxKeys = poBoxKeys.get(signature) || new Set();
      const completed = [...boxKeys].filter(key => boxes.get(key)?.scanned === boxes.get(key)?.total).length;
      return { label: row.label, bookingId: row.bookingId, progress: `${completed}/${boxKeys.size + (poPendingBoxes.get(signature) || 0)}` };
    });
    const itemRows = [...items.values()].map(row => ({
      label: row.label, bookingId: row.bookingId, orderNo: row.orderNo, total: row.total, scanned: row.scanned,
      boxCount: row.boxKeys.size + row.pendingBoxes, pendingBoxes: row.pendingBoxes, pendingItems: row.pendingItems,
      completedBoxes: [...row.boxKeys].filter(key => boxes.get(key)?.scanned === boxes.get(key)?.total).length,
      variantCount: row.variantKeys.size,
      markets: [...row.markets.values()].map(market => ({
        code: market.code, name: market.name, total: market.total, scanned: market.scanned,
        variants: [...market.variants.values()],
      })),
    }));
    state.sessionRows = { po: poRows, items: itemRows, boxes: progress(boxes), scans, editable };
    $('tab-po-count').textContent = String(state.sessionRows.po.length);
    $('tab-items-count').textContent = String(state.sessionRows.items.length);
    for (const filter of BOX_FILTERS) $('box-' + filter + '-count').textContent = String(state.sessionRows.boxes.filter(row => boxStatus(row) === filter).length);
    selectSessionTab(state.activeSessionTab);
    return storageReady;
  };
  const resetSessionNavigation = () => {
    closeItemDetail();
    state.renderedSessionId = null; state.activeSessionTab = 'po'; state.activeBoxFilter = 'not-scanned';
    state.boxSearch = ''; state.sessionRows = null; state.completing = false; state.completionProgress = null;
    renderCompletionProgress();
    lockCompletionNavigation(false);
    $('box-search').value = '';
  };
  const saveSession = async session => { state.session = session; await store.put('sessions', session); await store.put('meta', session.sessionId, 'currentSession'); await renderSession(); };
  const openSession = async sessionId => {
    resetSessionNavigation(); clearNotice();
    try { await saveSession(await api('session', { sessionId })); return true; }
    catch (error) {
      if (!navigator.onLine) {
        try {
          const cached = await store.get('sessions', sessionId);
          if (cached && cached.deviceId === state.device?.id) { await saveSession(cached); return true; }
        } catch { notice('error.offline_storage', 'danger'); return false; }
      }
      explain(error); return false;
    }
  };
  const localScanCounts = async () => {
    try {
      const counts = new Map();
      for (const scan of await store.all('scans')) counts.set(scan.sessionId, (counts.get(scan.sessionId) || 0) + 1);
      return counts;
    } catch { return new Map(); }
  };
  const sessionCards = (target, rows, emptyKey, active = false, scanCounts = new Map()) => {
    const parent = $(target); parent.replaceChildren();
    if (!rows.length) { const p = document.createElement('p'); p.className = 'text-muted'; p.textContent = i18n.text(emptyKey); parent.append(p); return; }
    for (const row of rows) {
      const card = document.createElement('article'); card.className = `rfid-session-card ${active ? 'is-active' : 'is-completed'}`;
      const title = document.createElement('div'); title.textContent = (row.bookingIds || []).join(', ') || row.sessionId;
      title.className = 'rfid-session-card-title';
      const top = node('div', 'rfid-card-top');
      top.append(node('span', 'rfid-status-pill', i18n.text(active ? 'ui.scanning_status' : 'ui.completed_status')));
      const timestamp = row.sessionCompletedAtUtc || row.sessionStartedAtUtc;
      const date = timestamp ? new Date(timestamp) : null;
      if (date && !Number.isNaN(date.getTime())) {
        const time = node('time', 'text-muted', date.toLocaleString(i18n.language === 'vi' ? 'vi-VN' : 'en-US', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric' }));
        time.dateTime = date.toISOString(); top.append(time);
      }
      const meta = node('div', 'rfid-card-meta text-muted');
      meta.append(node('div', '', `${i18n.text('ui.driver')}: ${row.driverFullName || '—'}`),
        node('div', '', i18n.text('ui.item_po', { po: (row.orderNos || []).join(', ') || '—' })));
      if (row.vehiclePlateNumber) meta.append(node('div', '', `${i18n.text('ui.vehicle')}: ${row.vehiclePlateNumber}`));
      const metrics = node('div', 'rfid-card-metrics');
      const count = active ? (scanCounts.get(row.sessionId) ?? row.totalScannedCount ?? 0) : (row.totalScannedCount || 0);
      const metricValues = active
        ? [['ui.metric_scanned', formatCount(count)], ['ui.total_items', formatCount(row.plannedItemCount)], ['ui.planned_boxes', formatCount(row.plannedBoxCount)]]
        : [['ui.metric_scanned', `${formatCount(count)}/${formatCount(row.plannedItemCount)}`], ['ui.metal_checked', formatCount(row.metalCheckedCount)], ['ui.scanned_boxes', `${formatCount(row.boxScannedCount)}/${formatCount(row.plannedBoxCount)}`]];
      for (const [label, number] of metricValues) {
        const metric = node('div'); metric.append(node('small', 'text-muted', i18n.text(label)), node('strong', '', number)); metrics.append(metric);
      }
      const actions = node('div', 'rfid-card-actions');
      const openButton = document.createElement('button'); openButton.type = 'button'; openButton.className = 'btn btn-default btn-sm mr-2 mt-2'; openButton.textContent = i18n.text(active ? 'ui.continue' : 'ui.view_details'); openButton.onclick = () => openSession(row.sessionId);
      actions.append(openButton);
      if (active) {
        const completeButton = document.createElement('button'); completeButton.type = 'button'; completeButton.className = 'btn btn-primary btn-sm mr-2 mt-2'; completeButton.textContent = i18n.text('ui.complete_short');
        completeButton.onclick = async () => { completeButton.disabled = true; try { if (await openSession(row.sessionId)) await beginCompletion(); } finally { completeButton.disabled = false; } };
        const deleteButton = document.createElement('button'); deleteButton.type = 'button'; deleteButton.className = 'btn btn-danger btn-sm mt-2'; deleteButton.textContent = i18n.text('ui.delete');
        deleteButton.onclick = async () => { deleteButton.disabled = true; try { await deleteSession(row.sessionId); } finally { deleteButton.disabled = false; } };
        actions.append(completeButton, deleteButton);
      }
      card.append(top, title, meta, metrics, actions); parent.append(card);
    }
  };
  const loadHome = async () => {
    if (!state.device) return views('device-view');
    views('home-view'); selectHomeTab(state.homeTab);
    $('device-summary').textContent = `${state.device.deviceName} · ${state.device.companyName}`;
    try {
      const [active, history, scanCounts] = await Promise.all([api('active'), api('history'), localScanCounts()]);
      sessionCards('active-list', active, 'ui.empty_sessions', true, scanCounts);
      sessionCards('history-list', history.items, 'ui.empty_history');
    } catch (error) {
      if (!navigator.onLine) {
        const [sessions, scanCounts] = await Promise.all([store.all('sessions'), localScanCounts()]);
        const cached = sessions.filter(s => s.deviceId === state.device.id);
        sessionCards('active-list', cached.filter(s => s.sessionStatus === 'Active'), 'ui.empty_sessions', true, scanCounts);
        sessionCards('history-list', cached.filter(s => s.sessionStatus === 'Completed'), 'ui.empty_history');
      } else explain(error);
    }
  };
  const activate = async id => {
    try {
      const device = await api('device_check', { deviceId: id });
      if (state.session && state.device?.id && state.device.id !== device.id) throw { code: 'error.device_session' };
      state.device = device; await store.put('meta', device, 'device');
      $('device-id').value = device.id; renderDeviceInfo(); stopCamera(); notice('success.device_ready', 'success');
      const returnView = state.returnView;
      state.returnView = null;
      if (returnView === 'session-view' && state.session) await renderSession();
      else await loadHome();
    } catch (error) { explain(error); }
  };
  const start = async () => {
    addBooking();
    const bookingIds = [...state.bookingIds];
    if (!bookingIds.length) return notice('error.bookings_required', 'danger');
    const button = $('start-session');
    if (button.disabled) return;
    button.disabled = true;
    button.textContent = i18n.text('ui.starting');
    try {
      const preview = await api('preview_conflicts', { bookingIds });
      const confirmConflicts = preview.sessions.length > 0;
      if (confirmConflicts && !window.confirm(i18n.text('ui.confirm_conflict'))) return;
      const result = await api('start', { bookingIds, confirmConflicts }, 'POST');
      const session = result?.session;
      if (!session?.sessionId) throw { code: 'error.unexpected' };
      resetScannerBuffer(); resetSessionNavigation();
      state.bookingIds = []; renderBookings();
      state.session = session;
      views('session-view');
      let cacheReady = true;
      try {
        await store.put('sessions', session);
        await store.put('meta', session.sessionId, 'currentSession');
      } catch { cacheReady = false; }
      const sessionRendered = await renderSession();
      if (cacheReady && sessionRendered) notice('success.session_started', 'success');
      else notice('error.offline_storage', 'warning');
    } catch (error) { explain(error); }
    finally { button.disabled = false; button.textContent = i18n.text('ui.start'); }
  };
  const addScan = async (rfid, sessionId, focusAfter = false) => {
    if (!state.session || state.session.sessionId !== sessionId || state.session.sessionStatus !== 'Active'
      || state.completing || state.completionPending) return;
    const lookupRfid = normalizedRfid(rfid);
    if (!lookupRfid) return;
    const bookings = state.session.preloadedBookings || [];
    const matches = bookings.flatMap(b => (b.items || []).filter(x => normalizedRfid(x.rfid) === lookupRfid).map(item => ({ booking: b, item })));
    if (!matches.length) return notice('error.scan_not_in_plan', 'danger');
    if (matches.length > 1) return notice('error.scan_ambiguous_in_plan', 'danger');
    let scans;
    try { scans = await scansForSession(); }
    catch { return notice('error.offline_storage', 'danger'); }
    if (state.session?.sessionId !== sessionId) return;
    if (scans.some(x => normalizedRfid(x.rfid) === lookupRfid)) return notice('error.scan_duplicate', 'danger');
    const { booking, item } = matches[0];
    const scan = { bookingId: booking.bookingId, finishedGoodPackDetailId: item.finishedGoodPackDetailId,
      rfid: item.rfid, orderNo: item.orderNo, doNo: item.doNo, dispPackNum: item.dispPackNum, scannedAtUtc: new Date().toISOString() };
    try {
      await store.put('scans', { key: `${sessionId}|${lookupRfid}`, sessionId, payload: scan });
      if (state.session?.sessionId !== sessionId) return;
      const input = $('rfid-input');
      if (normalizedRfid(input.value) === lookupRfid) input.value = '';
      if (focusAfter) input.focus();
      notice('success.scan_saved', 'success'); await renderSession();
    } catch { notice('error.offline_storage', 'danger'); }
  };
  const canCaptureScans = () => state.session?.sessionStatus === 'Active' && !state.completing && !state.completionPending && !state.scanPaused && !state.refreshing
    && !$('photo-dialog').open && !$('device-info-modal').open && !$('session-view').hidden && !$('scan-dock').hidden && $('item-detail-modal').hidden;
  const enqueueScan = (rfid, focusAfter = false, sessionId = state.session?.sessionId) => {
    if (!sessionId) return Promise.resolve();
    scanQueue = scanQueue.catch(() => {}).then(() => addScan(rfid, sessionId, focusAfter));
    return scanQueue;
  };
  const clearScannerCommitTimer = () => {
    if (scannerCommitTimer !== null) window.clearTimeout(scannerCommitTimer);
    scannerCommitTimer = null;
  };
  const resetFocusedRfidKeyBurst = () => {
    lastFocusedRfidKeyAt = 0;
    focusedRfidKeyBurst = 0;
  };
  const commitScannerInput = (focusAfter = false) => {
    clearScannerCommitTimer();
    resetFocusedRfidKeyBurst();
    if (!canCaptureScans()) return;
    const input = $('rfid-input');
    const rfid = input.value;
    if (!normalizedRfid(rfid)) return;
    const sessionId = state.session.sessionId;
    input.value = '';
    void enqueueScan(rfid, focusAfter, sessionId);
  };
  const resetScannerBuffer = () => {
    clearScannerCommitTimer(); resetFocusedRfidKeyBurst();
    $('rfid-input').value = '';
  };
  const queueScannerCommit = () => {
    clearScannerCommitTimer();
    scannerCommitTimer = window.setTimeout(() => {
      scannerCommitTimer = null;
      commitScannerInput();
    }, SCAN_COMMIT_DELAY_MS);
  };
  const appendScannerText = chunk => {
    if (!canCaptureScans()) return;
    const raw = String(chunk || '');
    if (!raw) return;
    const hasTerminator = /[\r\n\t]/.test(raw);
    const sanitized = raw.replace(/[\r\n\t]+/g, '');
    if (sanitized) $('rfid-input').value = `${$('rfid-input').value || ''}${sanitized}`;
    if (hasTerminator) commitScannerInput();
    else if (sanitized) queueScannerCommit();
  };
  const shouldCaptureScannerKeys = event => {
    if (!canCaptureScans() || event.target === $('rfid-input')) return false;
    const target = event.target;
    if (target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return false;
    return true;
  };
  const handleScannerKeyDown = event => {
    if (event.target === $('rfid-input')) {
      if ((event.key === 'Enter' || event.key === 'Tab') && normalizedRfid(event.target.value)) {
        event.preventDefault(); event.stopPropagation(); commitScannerInput(true);
      } else if (event.key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey && !event.isComposing) {
        const now = performance.now();
        focusedRfidKeyBurst = now - lastFocusedRfidKeyAt <= SCAN_COMMIT_DELAY_MS ? focusedRfidKeyBurst + 1 : 1;
        lastFocusedRfidKeyAt = now;
        if (focusedRfidKeyBurst >= 4) queueScannerCommit();
      } else if (event.key === 'Backspace') {
        focusedRfidKeyBurst = 0; lastFocusedRfidKeyAt = 0;
      }
      return;
    }
    if (!shouldCaptureScannerKeys(event)) return;
    const input = $('rfid-input');
    if (event.key === 'Enter' || event.key === 'Tab') {
      if (!normalizedRfid(input.value)) return;
      event.preventDefault(); event.stopPropagation(); commitScannerInput(); return;
    }
    if (event.key === 'Backspace') {
      if (!input.value) return;
      event.preventDefault(); event.stopPropagation(); input.value = input.value.slice(0, -1); queueScannerCommit(); return;
    }
    if (event.key.length !== 1 || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) return;
    event.preventDefault(); event.stopPropagation(); appendScannerText(event.key);
  };
  const handleScannerBeforeInput = event => {
    if (!canCaptureScans()) return;
    const text = typeof event.data === 'string' ? event.data : '';
    if (event.target === $('rfid-input')) {
      if (event.inputType === 'insertLineBreak') {
        event.preventDefault(); commitScannerInput(true);
      } else if (text && /[\r\n\t]/.test(text)) {
        event.preventDefault(); appendScannerText(text);
      }
      return;
    }
    if (!shouldCaptureScannerKeys(event) || !text) return;
    event.preventDefault(); event.stopPropagation(); appendScannerText(text);
  };
  const handleScannerPaste = event => {
    if (!canCaptureScans()) return;
    if (event.target !== $('rfid-input') && !shouldCaptureScannerKeys(event)) return;
    const text = event.clipboardData?.getData('text');
    if (!text) return;
    event.preventDefault();
    if (event.target !== $('rfid-input')) event.stopPropagation();
    appendScannerText(text);
  };
  const beginCompletion = async () => {
    if (!state.session || state.session.sessionStatus !== 'Active') return;
    if (!navigator.onLine) return notice('ui.network_required', 'warning');
    try {
      await scanQueue;
      const beforeCount = (await scansForSession()).length;
      const pendingRfid = normalizedRfid($('rfid-input').value);
      if (pendingRfid) {
        commitScannerInput();
        await scanQueue;
        const afterPendingScan = await scansForSession();
        if (afterPendingScan.length === beforeCount) return;
      }
      const scans = await scansForSession();
      if (!scans.length) return notice('error.scan_required', 'danger');
      $('completion-vehicle').value = state.session.vehiclePlateNumber || '';
      $('completion-driver').value = state.session.driverFullName || '';
      $('completion-note').value = state.session.note || '';
      state.completing = true;
      state.completionProgress = null;
      renderCompletionProgress();
      lockCompletionNavigation(true);
      show('completion-form', true); show('scan-dock', false); show('scan-dock-spacer', false);
      clearNotice(); $('completion-form').scrollIntoView({ block: 'start' });
      ($('completion-vehicle').value ? ($('completion-driver').value ? $('completion-note') : $('completion-driver')) : $('completion-vehicle')).focus();
    } catch { notice('error.offline_storage', 'danger'); }
  };
  const cancelCompletion = () => {
    if (state.completionPending) return;
    state.completing = false;
    state.completionProgress = null;
    renderCompletionProgress();
    lockCompletionNavigation(false);
    show('completion-form', false); show('scan-dock', true); show('scan-dock-spacer', true);
    clearNotice(); $('rfid-input').focus();
  };
  const complete = async () => {
    if (!state.completing || state.completionPending || state.session?.sessionStatus !== 'Active') return;
    if (!navigator.onLine) return notice('ui.network_required', 'warning');
    const vehiclePlateNumber = value('completion-vehicle'), driverFullName = value('completion-driver');
    if (!vehiclePlateNumber || !driverFullName) {
      notice('error.session_header', 'danger');
      $(vehiclePlateNumber ? 'completion-driver' : 'completion-vehicle').focus();
      return;
    }
    state.completionPending = true;
    const pendingControls = ['confirm-completion', 'cancel-completion', 'completion-photos'];
    for (const id of pendingControls) $(id).disabled = true;
    let total = 0;
    try {
      if (!await window.RfidPhotos.prepareCompletion(state.session.sessionId)) return;
      const scans = await scansForSession();
      total = scans.length;
      state.completionProgress = { phase: 'uploading', uploaded: 0, total };
      renderCompletionProgress();
      const session = await api('complete', { sessionId: state.session.sessionId, scans,
        vehiclePlateNumber, driverFullName, note: value('completion-note') }, 'POST');
      const uploaded = Number(session.totalScannedCount ?? scans.length);
      state.completionProgress = { phase: 'complete', uploaded, total: scans.length };
      state.completing = false;
      lockCompletionNavigation(false);
      let cacheReady = true;
      try { await store.clearScans(session.sessionId); } catch { cacheReady = false; }
      try { await store.put('sessions', session); } catch { cacheReady = false; }
      try { await store.remove('meta', 'currentSession'); } catch { cacheReady = false; }
      state.session = null;
      resetSessionNavigation();
      await loadHome();
      notice(cacheReady ? 'ui.uploaded_records' : 'ui.uploaded_records_cache_warning', cacheReady ? 'success' : 'warning', {
        uploaded: formatCount(uploaded), total: formatCount(scans.length),
      });
    } catch (error) {
      state.completionProgress = { phase: 'failed', uploaded: 0, total };
      renderCompletionProgress();
      explain(error);
    }
    finally { state.completionPending = false; for (const id of pendingControls) $(id).disabled = false; }
  };
  const deleteSession = async sessionId => {
    if (!sessionId || !window.confirm(i18n.text('ui.confirm_delete'))) return;
    try { await api('delete', { sessionId }, 'POST'); }
    catch (error) { explain(error); return; }
    let cacheError = false;
    try {
      await store.clearScans(sessionId);
      await store.remove('sessions', sessionId);
      if (await store.get('meta', 'currentSession') === sessionId) await store.remove('meta', 'currentSession');
    } catch { cacheError = true; }
    if (state.session?.sessionId === sessionId) { state.session = null; resetSessionNavigation(); }
    await loadHome(); notice(cacheError ? 'error.offline_storage' : 'success.session_deleted', cacheError ? 'danger' : 'success');
  };
  const stopCamera = () => {
    if (state.cameraTimer) clearInterval(state.cameraTimer);
    state.cameraTimer = null;
    if (state.stream) state.stream.getTracks().forEach(track => track.stop());
    state.stream = null; $('qr-video').srcObject = null; show('camera-preview', false);
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
      show('camera-preview', true);
      const video = $('qr-video'); video.srcObject = state.stream; await video.play();
      $('camera-status').textContent = i18n.text('ui.camera_scanning');
      state.cameraTimer = setInterval(async () => {
        if (!state.stream || video.readyState < 2) return;
        try { const codes = await detector.detect(video); if (codes.length) { const id = parseDeviceId(codes[0].rawValue); stopCamera(); $('device-id').value = id; await activate(id); } }
        catch { /* Keep the camera open for the next frame. */ }
      }, 500);
    } catch { stopCamera(); notice('error.camera_failed', 'danger'); }
  };
  const selectHomeTab = (name, focus = false) => {
    state.homeTab = name;
    for (const tab of ['active', 'history']) {
      const selected = tab === name;
      const button = $(`home-tab-${tab}`);
      button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1;
      show(`home-${tab}-panel`, selected);
      if (selected && focus) button.focus();
    }
  };
  const renderBookings = () => {
    const list = $('booking-chips'); list.replaceChildren();
    $('booking-ids').value = state.bookingIds.join('\n');
    if (!state.bookingIds.length) list.append(node('p', 'rfid-empty', i18n.text('ui.empty_bookings')));
    for (const booking of state.bookingIds) {
      const chip = node('div', 'rfid-booking-chip');
      const remove = node('button', '', '×'); remove.type = 'button';
      remove.setAttribute('aria-label', i18n.text('ui.remove_booking', { booking }));
      remove.onclick = () => { state.bookingIds = state.bookingIds.filter(id => id !== booking); renderBookings(); $('booking-entry').focus(); };
      chip.append(node('span', '', booking), remove); list.append(chip);
    }
  };
  const addBooking = () => {
    const entered = value('booking-entry').split(/[\n,;\s]+/).map(normalized).filter(Boolean);
    state.bookingIds = [...new Set([...state.bookingIds, ...entered])];
    $('booking-entry').value = ''; renderBookings();
  };
  const renderScanMode = () => {
    $('toggle-scan').textContent = i18n.text(state.scanPaused ? 'ui.resume_scan' : 'ui.pause_scan');
    $('toggle-scan').setAttribute('aria-pressed', String(state.scanPaused));
    $('rfid-input').disabled = state.scanPaused || state.refreshing;
  };
  const refreshSession = async () => {
    if (state.refreshing || state.session?.sessionStatus !== 'Active') return;
    if (!navigator.onLine) return notice('ui.network_required', 'warning');
    state.refreshing = true; resetScannerBuffer(); renderScanMode();
    const controls = ['back-home', 'device-settings', 'refresh-session', 'complete-session', 'toggle-scan'];
    controls.forEach(id => { $(id).disabled = true; });
    try {
      await scanQueue;
      for (const booking of [...(state.session.preloadedBookings || [])]) {
        const result = await api('refresh_delta', { sessionId: state.session.sessionId, bookingId: booking.bookingId }, 'POST');
        await saveSession(result.session);
      }
      notice('success.booking_refreshed', 'success');
    } catch (error) { explain(error); }
    finally {
      state.refreshing = false; controls.forEach(id => { $(id).disabled = false; }); renderScanMode();
    }
  };
  const init = async () => {
    expandPageShell();
    i18n.render(); renderNetwork();
    window.RfidPhotos.init({ api, context: () => ({ deviceId: state.device?.id, sessionId: state.session?.sessionId }) });
    window.addEventListener('online', renderNetwork); window.addEventListener('offline', renderNetwork);
    $('activate-device').onclick = () => activate(value('device-id'));
    $('check-device').onclick = () => activate(value('device-id'));
    $('device-id').onkeydown = event => { if (event.key === 'Enter') activate(value('device-id')); };
    $('scan-qr').onclick = scanQr;
    $('device-settings').onclick = () => {
      resetScannerBuffer();
      if (!state.device) { views('device-view'); $('device-id').focus(); return; }
      $('info-device-id').textContent = state.device.id;
      $('info-device-name').textContent = state.device.deviceName || i18n.text('ui.not_available');
      $('info-company').textContent = state.device.companyName || i18n.text('ui.not_available');
      $('device-info-modal').showModal();
    };
    $('close-device-info').onclick = () => $('device-info-modal').close();
    $('manage-device').onclick = () => {
      $('device-info-modal').close();
      if (!state.returnView) state.returnView = $('session-view').hidden ? 'home-view' : 'session-view';
      $('device-id').value = state.device.id;
      renderDeviceInfo(); clearNotice(); views('device-view');
    };
    $('return-to-app').onclick = async () => {
      const returnView = state.returnView;
      state.returnView = null;
      clearNotice();
      if (returnView === 'session-view' && state.session) await renderSession();
      else await loadHome();
    };
    $('change-device').onclick = async () => { if (!window.confirm(i18n.text('ui.confirm_change_device'))) return; $('device-info-modal').close(); resetScannerBuffer(); stopCamera(); state.returnView = null; state.device = null; state.session = null; resetSessionNavigation(); renderDeviceInfo(); $('device-id').value = ''; await store.remove('meta', 'device'); await store.remove('meta', 'currentSession'); clearNotice(); views('device-view'); };
    $('start-session').onclick = start;
    $('add-booking').onclick = addBooking;
    $('booking-entry').onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); addBooking(); } };
    for (const button of document.querySelectorAll('[data-home-tab]')) {
      button.onclick = () => selectHomeTab(button.dataset.homeTab);
      button.onkeydown = event => navigateTabsWithKeyboard(event, ['active', 'history'], state.homeTab, selectHomeTab);
    }
    renderBookings();
    $('refresh-active').onclick = loadHome; $('refresh-history').onclick = loadHome;
    $('back-home').onclick = async () => { resetScannerBuffer(); state.session = null; resetSessionNavigation(); await store.remove('meta', 'currentSession'); await loadHome(); };
    $('toggle-scan').onclick = () => {
      resetScannerBuffer(); state.scanPaused = !state.scanPaused; renderScanMode();
      if (!state.scanPaused) $('rfid-input').focus();
    };
    $('refresh-session').onclick = refreshSession;
    $('theme-toggle').onclick = () => {
      const dark = $('rfid-app').classList.toggle('rfid-dark');
      $('theme-toggle').setAttribute('aria-pressed', String(dark));
      $('theme-toggle').textContent = dark ? '☀' : '☾';
      try { localStorage.setItem('rfid-theme', dark ? 'dark' : 'light'); } catch { /* Theme is optional. */ }
    };
    try { if (localStorage.getItem('rfid-theme') === 'dark') $('theme-toggle').click(); } catch { /* Theme is optional. */ }
    document.addEventListener('keydown', handleScannerKeyDown);
    document.addEventListener('beforeinput', handleScannerBeforeInput);
    document.addEventListener('paste', handleScannerPaste);
    $('complete-session').onclick = beginCompletion;
    $('cancel-completion').onclick = cancelCompletion; $('confirm-completion').onclick = complete;
    for (const button of document.querySelectorAll('[data-session-tab]')) {
      button.onclick = () => { state.boxScope = null; selectSessionTab(button.dataset.sessionTab); };
      button.onkeydown = event => navigateTabsWithKeyboard(event, SESSION_TABS, button.dataset.sessionTab, selectSessionTab);
    }
    for (const button of document.querySelectorAll('[data-box-filter]')) {
      button.onclick = () => selectBoxFilter(button.dataset.boxFilter);
      button.onkeydown = event => navigateTabsWithKeyboard(event, BOX_FILTERS, button.dataset.boxFilter, selectBoxFilter);
    }
    $('box-search').oninput = () => { state.boxSearch = value('box-search').toLocaleLowerCase(); renderBoxList(); };
    $('clear-box-search').onclick = () => { $('box-search').value = ''; state.boxSearch = ''; state.boxScope = null; renderBoxList(); $('box-search').focus(); };
    $('close-item-detail').onclick = closeItemDetail;
    $('item-detail-modal').onclick = event => { if (event.target === $('item-detail-modal')) closeItemDetail(); };
    $('item-detail-modal').onkeydown = event => {
      if (event.key === 'Escape') { event.preventDefault(); closeItemDetail(); }
      else if (event.key === 'Tab') { event.preventDefault(); $('close-item-detail').focus(); }
    };
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
