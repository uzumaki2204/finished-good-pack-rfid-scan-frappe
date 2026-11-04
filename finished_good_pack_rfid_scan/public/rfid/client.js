(() => {
  'use strict';
  const i18n = window.RfidI18n;
  const store = window.RfidOffline;
  const $ = id => document.getElementById(id);
  const state = { device: null, session: null, renderedSessionId: null, stream: null, cameraTimer: null, returnView: null,
    activeSessionTab: 'po', activeBoxFilter: 'not-scanned', boxSearch: '', sessionRows: null, completing: false, completionPending: false };
  const SESSION_TABS = ['po', 'items', 'boxes', 'sync'];
  const BOX_FILTERS = ['not-scanned', 'scanning', 'completed'];
  const COMPLETION_LOCKED_CONTROLS = ['back-home', 'device-settings', 'refresh-booking', 'rehydrate-plan', 'delete-session'];
  const normalized = value => String(value || '').trim().toUpperCase();
  const formatCount = count => Number(count || 0).toLocaleString(i18n.language === 'vi' ? 'vi-VN' : 'en-US');
  const node = (tag, className = '', label = '') => { const element = document.createElement(tag); element.className = className; element.textContent = label; return element; };
  const value = id => $(id).value.trim();
  const show = (id, visible) => { $(id).hidden = !visible; };
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
    for (const id of ['device-view', 'home-view', 'session-view']) show(id, id === name);
    show('back-home', name === 'session-view');
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
    if (state.activeSessionTab === 'po') table('po-list', [['ui.po', row => row.label || i18n.text('ui.not_available')], ['ui.boxes', row => row.progress]], rows.po, 'ui.empty_rows', 'table table-borderless mb-0');
    else if (state.activeSessionTab === 'items') renderItemList(rows.items);
    else if (state.activeSessionTab === 'boxes') renderBoxList();
    else {
      $('sync-status').textContent = i18n.text(state.session?.sessionStatus === 'Completed' ? 'ui.sync_complete' : 'ui.sync_local', { count: rows.scans.length });
      const columns = [['ui.scan_rfid', row => row.rfid], ['ui.po', row => row.orderNo], ['ui.boxes', row => row.dispPackNum]];
      if (rows.editable) columns.push(['ui.delete', row => {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-default btn-sm'; button.textContent = i18n.text('ui.remove_scan');
        button.onclick = async () => {
          try { await store.remove('scans', `${state.session.sessionId}|${normalized(row.rfid)}`); notice('success.scan_removed', 'success'); await renderSession(); }
          catch { notice('error.offline_storage', 'danger'); }
        };
        return button;
      }]);
      table('scan-list', columns, rows.scans, 'ui.empty_scans');
    }
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
      state.renderedSessionId = s.sessionId;
      state.activeSessionTab = 'po'; state.activeBoxFilter = 'not-scanned'; state.boxSearch = ''; state.completing = false;
      $('box-search').value = '';
    }
    views('session-view');
    const local = s.sessionStatus === 'Completed' ? [] : await scansForSession();
    const scans = s.sessionStatus === 'Completed' ? (s.scannedItems || []) : local;
    const plannedItems = (s.preloadedBookings || []).flatMap(b => (b.items || []).map(item => ({ ...item, bookingId: b.bookingId })));
    const plannedById = new Map(plannedItems.map(item => [`${item.bookingId}|${item.finishedGoodPackDetailId}`, item]));
    const metalCount = scans.filter(scan => {
      const item = plannedById.get(`${scan.bookingId}|${scan.finishedGoodPackDetailId}`);
      return ['Y', 'YES', 'TRUE', '1'].includes(normalized(item?.isMetalCheck || scan.isMetalCheck));
    }).length;
    const editable = s.sessionStatus === 'Active';
    if (!editable) state.completing = false;
    lockCompletionNavigation(editable && state.completing);
    show('scan-dock', editable && !state.completing);
    show('scan-dock-spacer', editable && !state.completing);
    show('completion-form', editable && state.completing);
    show('sync-actions', editable);
    show('completed-details', s.sessionStatus === 'Completed');
    $('completed-vehicle').textContent = s.vehiclePlateNumber || i18n.text('ui.not_available');
    $('completed-driver').textContent = s.driverFullName || i18n.text('ui.not_available');
    $('completed-note').textContent = s.note || i18n.text('ui.not_available');
    const warnings = s.planningWarnings || [];
    show('session-warnings', warnings.length > 0); $('session-warnings').replaceChildren(...warnings.map(w => { const p = document.createElement('p'); p.textContent = w; return p; }));
    const bookingSelect = $('booking-select');
    const selectedBooking = bookingSelect.value;
    bookingSelect.replaceChildren(...(s.bookingIds || []).map(id => { const option = document.createElement('option'); option.value = id; option.textContent = id; return option; }));
    if ((s.bookingIds || []).includes(selectedBooking)) bookingSelect.value = selectedBooking;
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
          const row = map.get(signature) || { label, total: 0, scanned: 0 };
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
      return { label: row.label, progress: `${completed}/${boxKeys.size + (poPendingBoxes.get(signature) || 0)}` };
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
    $('tab-sync-count').textContent = String(scans.length);
    for (const filter of BOX_FILTERS) $('box-' + filter + '-count').textContent = String(state.sessionRows.boxes.filter(row => boxStatus(row) === filter).length);
    selectSessionTab(state.activeSessionTab);
  };
  const resetSessionNavigation = () => {
    closeItemDetail();
    state.renderedSessionId = null; state.activeSessionTab = 'po'; state.activeBoxFilter = 'not-scanned';
    state.boxSearch = ''; state.sessionRows = null; state.completing = false;
    lockCompletionNavigation(false);
    $('box-search').value = '';
  };
  const saveSession = async session => { state.session = session; await store.put('sessions', session); await store.put('meta', session.sessionId, 'currentSession'); await renderSession(); };
  const openSession = async sessionId => {
    resetSessionNavigation();
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
      const card = document.createElement('div'); card.className = 'border rounded p-2 mb-2';
      const title = document.createElement('div'); title.textContent = (row.bookingIds || []).join(', ') || row.sessionId;
      const meta = document.createElement('small'); meta.className = 'text-muted d-block';
      meta.textContent = [row.vehiclePlateNumber, i18n.text('ui.scan_count', { count: active ? (scanCounts.get(row.sessionId) ?? row.totalScannedCount ?? 0) : (row.totalScannedCount || 0) })].filter(Boolean).join(' · ');
      const actions = document.createElement('div'); actions.className = 'd-flex flex-wrap align-items-center';
      const openButton = document.createElement('button'); openButton.type = 'button'; openButton.className = 'btn btn-default btn-sm mr-2 mt-2'; openButton.textContent = i18n.text('ui.resume'); openButton.onclick = () => openSession(row.sessionId);
      actions.append(openButton);
      if (active) {
        const completeButton = document.createElement('button'); completeButton.type = 'button'; completeButton.className = 'btn btn-primary btn-sm mr-2 mt-2'; completeButton.textContent = i18n.text('ui.complete');
        completeButton.onclick = async () => { completeButton.disabled = true; try { if (await openSession(row.sessionId)) await beginCompletion(); } finally { completeButton.disabled = false; } };
        const deleteButton = document.createElement('button'); deleteButton.type = 'button'; deleteButton.className = 'btn btn-danger btn-sm mt-2'; deleteButton.textContent = i18n.text('ui.delete');
        deleteButton.onclick = async () => { deleteButton.disabled = true; try { await deleteSession(row.sessionId); } finally { deleteButton.disabled = false; } };
        actions.append(completeButton, deleteButton);
      }
      card.append(title, meta, actions); parent.append(card);
    }
  };
  const loadHome = async () => {
    if (!state.device) return views('device-view');
    views('home-view');
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
    const bookingIds = value('booking-ids').split(/[\n,;]+/).map(x => x.trim()).filter(Boolean);
    if (!bookingIds.length) return notice('error.bookings_required', 'danger');
    try {
      const preview = await api('preview_conflicts', { bookingIds });
      const confirmConflicts = preview.sessions.length > 0;
      if (confirmConflicts && !window.confirm(i18n.text('ui.confirm_conflict'))) return;
      const result = await api('start', { bookingIds, confirmConflicts }, 'POST');
      resetSessionNavigation(); await saveSession(result.session); notice('success.session_started', 'success');
    } catch (error) { explain(error); }
  };
  const addScan = async () => {
    if (!state.session || state.session.sessionStatus !== 'Active' || state.completing) return;
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
  const beginCompletion = async () => {
    if (!state.session || state.session.sessionStatus !== 'Active') return;
    if (!navigator.onLine) return notice('ui.network_required', 'warning');
    try {
      const scans = await scansForSession();
      if (!scans.length) return notice('error.scan_required', 'danger');
      $('completion-vehicle').value = state.session.vehiclePlateNumber || '';
      $('completion-driver').value = state.session.driverFullName || '';
      $('completion-note').value = state.session.note || '';
      state.completing = true;
      lockCompletionNavigation(true);
      show('completion-form', true); show('scan-dock', false); show('scan-dock-spacer', false);
      clearNotice(); $('completion-form').scrollIntoView({ block: 'start' });
      ($('completion-vehicle').value ? ($('completion-driver').value ? $('completion-note') : $('completion-driver')) : $('completion-vehicle')).focus();
    } catch { notice('error.offline_storage', 'danger'); }
  };
  const cancelCompletion = () => {
    if (state.completionPending) return;
    state.completing = false;
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
    const pendingControls = ['confirm-completion', 'cancel-completion'];
    for (const id of pendingControls) $(id).disabled = true;
    try {
      const scans = await scansForSession();
      const session = await api('complete', { sessionId: state.session.sessionId, scans,
        vehiclePlateNumber, driverFullName, note: value('completion-note') }, 'POST');
      state.completing = false;
      lockCompletionNavigation(false);
      try { await store.clearScans(session.sessionId); await saveSession(session); }
      catch { state.session = session; await renderSession(); return notice('error.offline_storage', 'danger'); }
      notice('success.session_completed', 'success');
    } catch (error) { explain(error); }
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
    expandPageShell();
    i18n.render(); renderNetwork();
    window.addEventListener('online', renderNetwork); window.addEventListener('offline', renderNetwork);
    $('activate-device').onclick = () => activate(value('device-id'));
    $('check-device').onclick = () => activate(value('device-id'));
    $('device-id').onkeydown = event => { if (event.key === 'Enter') activate(value('device-id')); };
    $('scan-qr').onclick = scanQr;
    $('device-settings').onclick = () => {
      if (!state.device) { views('device-view'); $('device-id').focus(); return; }
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
    $('change-device').onclick = async () => { stopCamera(); state.returnView = null; state.device = null; state.session = null; resetSessionNavigation(); renderDeviceInfo(); $('device-id').value = ''; await store.remove('meta', 'device'); await store.remove('meta', 'currentSession'); clearNotice(); views('device-view'); };
    $('start-session').onclick = start;
    $('refresh-active').onclick = loadHome; $('refresh-history').onclick = loadHome;
    $('back-home').onclick = async () => { state.session = null; resetSessionNavigation(); await store.remove('meta', 'currentSession'); await loadHome(); };
    $('add-scan').onclick = addScan; $('rfid-input').onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); addScan(); } };
    $('complete-session').onclick = beginCompletion;
    $('cancel-completion').onclick = cancelCompletion; $('confirm-completion').onclick = complete;
    $('delete-session').onclick = () => deleteSession(state.session?.sessionId);
    $('refresh-booking').onclick = refreshBooking; $('rehydrate-plan').onclick = rehydrate;
    for (const button of document.querySelectorAll('[data-session-tab]')) {
      button.onclick = () => selectSessionTab(button.dataset.sessionTab);
      button.onkeydown = event => navigateTabsWithKeyboard(event, SESSION_TABS, button.dataset.sessionTab, selectSessionTab);
    }
    for (const button of document.querySelectorAll('[data-box-filter]')) {
      button.onclick = () => selectBoxFilter(button.dataset.boxFilter);
      button.onkeydown = event => navigateTabsWithKeyboard(event, BOX_FILTERS, button.dataset.boxFilter, selectBoxFilter);
    }
    $('box-search').oninput = () => { state.boxSearch = value('box-search').toLocaleLowerCase(); renderBoxList(); };
    $('clear-box-search').onclick = () => { $('box-search').value = ''; state.boxSearch = ''; renderBoxList(); $('box-search').focus(); };
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
