(() => {
  'use strict';
  const API = 'finished_good_pack_rfid_scan.reporting.';
  const pending = 'Chưa đồng bộ dữ liệu scan';
  const number = new Intl.NumberFormat('vi-VN');
  const dates = new Intl.DateTimeFormat('vi-VN', {timeZone: 'Asia/Ho_Chi_Minh', dateStyle: 'short', timeStyle: 'medium'});
  const text = value => value === null || value === undefined || value === '' ? '—' : String(value);
  const stamp = value => value ? dates.format(new Date(value)) : '—';
  const count = value => value == null ? pending : number.format(value);
  const node = (tag, content, className) => {
    const el = document.createElement(tag);
    if (content !== undefined) el.textContent = content;
    if (className) el.className = className;
    return el;
  };
  const button = (label, action, className = 'btn btn-default btn-sm') => {
    const el = node('button', label, className); el.type = 'button'; el.onclick = action; return el;
  };
  const iconButton = (label, iconPath, action) => {
    const el = button('', action, 'btn btn-default rfid-report-action');
    const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    for (const [key, value] of Object.entries({width:16,height:16,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':1.8,'stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'})) icon.setAttribute(key,value);
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d',iconPath);
    icon.append(path); el.append(icon,node('span',label)); return el;
  };
  const printButton = action => iconButton('In','M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v7H6zM18 12h.01',action);
  const refreshButton = action => iconButton('Làm mới','M20 7v5h-5M4 17v-5h5M6.1 6.1A8 8 0 0 1 19.7 10M4.3 14A8 8 0 0 0 17.9 17.9',action);
  const viewButton = action => iconButton('Xem phiên','M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',action);
  const backButton = action => iconButton('Tổng quan','M19 12H5m6-6-6 6 6 6',action);
  let searchId = 0;
  const searchable = (wrap, name, placeholder) => {
    const el = node('input',undefined,'form-control');el.type='text';el.name=name;el.placeholder=placeholder;el.autocomplete='off';
    const list = node('datalist');list.id=`rfid-filter-search-${++searchId}`;el.setAttribute('list',list.id);el._choices=list;
    el.oninput=()=>el.setCustomValidity('');
    el.validateChoice=()=>{el.setCustomValidity(!el.value || Array.from(list.options).some(o=>o.value===el.value)?'':'Vui lòng chọn một mã trong danh sách gợi ý.');return el.reportValidity();};
    wrap.append(el,list);return el;
  };
  const call = async (method, args = {}) => {
    const response = await frappe.call({method: API + method, args, type: 'GET'});
    if (!response || response.exc || response.message === undefined) throw new Error('Không thể tải báo cáo. Vui lòng thử lại.');
    return response.message;
  };
  const overviewColumns = [
    ['company','Công ty'], ['orderNos','PO', v => v.join(', ')], ['bookingIds','Booking', v => v.join(', ')],
    ['status','Trạng thái', v => v === 'Completed' ? 'Đã hoàn thành' : 'Đang scan'],
    ['vehicle','Biển số xe'], ['driver','Tài xế'], ['note','Ghi chú'],
    ['startedAt','Bắt đầu',stamp], ['completedAt','Hoàn thành',stamp],
    ['scannedItems','Hàng scan',count], ['plannedItems','Hàng kế hoạch',count], ['metalChecked','Rà kim',count],
    ['scannedBoxes','Thùng scan',count], ['plannedBoxes','Thùng kế hoạch',count], ['device','Thiết bị'], ['sessionId','Mã phiên']
  ];
  const detailColumns = [
    ['booking','Booking'], ['po','PO'], ['do','DO'], ['item','Mã hàng'], ['marketCode','Mã thị trường'],
    ['marketName','Thị trường'], ['colorCode','Mã màu'], ['colorName','Tên màu'], ['sizeCode','Mã size'],
    ['sizeName','Tên size'], ['metal','Rà kim'], ['box','Số thùng'], ['boxCode','Code thùng'],
    ['rfid','RFID'], ['scannedAt','Thời gian scan',stamp]
  ];
  function table(columns, rows, onOpen) {
    const scroll = node('div', undefined, 'rfid-report-table');
    const tableEl = node('table', undefined, 'table table-bordered');
    const header = node('tr');
    if (onOpen) header.append(node('th','Chi tiết'));
    columns.forEach(([, label]) => {const th = node('th', label); th.scope = 'col'; header.append(th);});
    const head = node('thead'); head.append(header); tableEl.append(head);
    const body = node('tbody');
    rows.forEach(row => {
      const tr = node('tr');
      if (onOpen) {const td = node('td'); td.append(viewButton(() => onOpen(row.sessionId))); tr.append(td);}
      columns.forEach(([key,, format]) => tr.append(node('td', text(format ? format(row[key]) : row[key]))));
      body.append(tr);
    });
    if (!rows.length) {const td = node('td','Không có dữ liệu.'); td.colSpan = columns.length + (onOpen ? 1 : 0); const tr = node('tr');tr.append(td);body.append(tr);}
    tableEl.append(body); scroll.append(tableEl); return scroll;
  }
  function pager(data, change) {
    const row = node('div', undefined, 'rfid-report-pager');
    const previous = button('Trang trước', () => change(data.page - 1)); previous.disabled = data.page <= 1;
    const next = button('Trang sau', () => change(data.page + 1)); next.disabled = data.page * data.pageSize >= data.total;
    row.append(node('span', `${number.format(data.total)} dòng · Trang ${data.page}/${Math.max(1, Math.ceil(data.total / data.pageSize))}`), previous, next);
    return row;
  }
  function mount(page) {
    const root = node('div', undefined, 'rfid-report'); page.main.append(root);
    const pageHead = root.closest('.page-container')?.querySelector('.page-head');
    pageHead?.classList.add('rfid-report-page-head');
    const setHeading = detail => page.set_title(detail ? 'BÁO CÁO CHI TIẾT SCAN RFID LOAD CONT' : 'BÁO CÁO TỔNG QUAN SCAN RFID LOAD CONT');
    const filters = node('form', undefined, 'rfid-report-filters');
    const fields = {};
    const now = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    const input = (key,label,type='text',value='') => {
      const wrap = node('label',label);
      if(type==='search'){const el=searchable(wrap,key,'Gõ để tìm '+label);filters.append(wrap);fields[key]=el;return el;}
      const el = node(type === 'select' ? 'select':'input', undefined, 'form-control');
      if (type !== 'select') el.type = type;
      el.name = key; el.value = value; wrap.append(el); filters.append(wrap); fields[key] = el; return el;
    };
    input('from_date','Từ ngày','date',now.slice(0,8)+'01'); input('to_date','Đến ngày','date',now);
    input('company','Công ty','select'); input('device','Thiết bị','select'); input('status','Trạng thái','select');
    input('booking','Booking','search'); input('po','PO','search');
    const option = (select,label,value='') => {if(select._choices && !value)return;const el = node('option',label);el.value = value;(select._choices||select).append(el);};
    option(fields.company,'Tất cả công ty'); option(fields.device,'Tất cả thiết bị');
    option(fields.status,'Tất cả trạng thái'); option(fields.booking,'Tất cả Booking'); option(fields.po,'Tất cả PO');
    const load = refreshButton(() => overview(1));
    const print = printButton(() => {}); print.disabled = true;
    const filterActions = node('div', undefined, 'rfid-report-filter-actions');
    filterActions.append(load,print); filters.append(filterActions);
    const info = node('p','','text-danger'); info.hidden = true;
    const content = node('section'); root.append(filters,info,content);
    let request = 0, selected = null, overviewPage = 1, devices = [], detailFilters = {}, detailPageSize = 100;
    function printReport(args) {
      window.open('/api/method/' + API + 'print_report?' + new URLSearchParams(args), '_blank', 'noopener');
    }
    function error(target, action) {target.replaceChildren(node('p','Không thể tải dữ liệu. Vui lòng kiểm tra quyền truy cập hoặc thử lại.','text-danger'),button('Thử lại',action));}
    async function overview(pageIndex=1) {
      if(![fields.booking,fields.po].every(el=>el.validateChoice())) return;
      const seq = ++request; selected = null; overviewPage = pageIndex; setHeading(false); root.classList.remove("rfid-report-detail");
      filters.hidden = false; info.hidden = !info.textContent; print.disabled = true; content.replaceChildren(node('p','Đang tải báo cáo…'));
      const args = Object.fromEntries(Object.entries(fields).map(([key,el]) => [key, el.value.trim()]));
      if (!args.from_date || !args.to_date || args.from_date > args.to_date) {content.replaceChildren(node('p','Vui lòng chọn khoảng ngày hợp lệ.','text-danger'));return;}
      try {
        const data = await call('overview', {...args,page:pageIndex}); if(seq !== request) return;
        print.onclick = () => printReport(args); print.disabled = false;
        content.replaceChildren(table(overviewColumns,data.items,open),pager(data,overview));
      } catch {if(seq === request) error(content,()=>overview(pageIndex));}
    }
    async function open(id,pageIndex=1) {
      if (selected !== id) detailFilters = {};
      const appliedDetailFilters = {...detailFilters};
      const seq = ++request; selected = id; setHeading(true); root.classList.add("rfid-report-detail"); filters.hidden = true; info.hidden = true;
      content.replaceChildren(node('p','Đang tải chi tiết…'));
      try {
        const data = await call('detail',{session_id:id,page:pageIndex,page_size:detailPageSize,...appliedDetailFilters}); if(seq !== request) return;
        const header = node('div',undefined,'rfid-report-actions'); header.append(backButton(()=>overview(overviewPage)),refreshButton(()=>open(id,pageIndex)),printButton(()=>printReport({session_id:id,...appliedDetailFilters})));
        const session = data.session;
        const completed = session.status === 'Completed';
        const heading = node('div',undefined,'rfid-detail-heading');
        const headingText = node('div');
        headingText.append(node('span','CHI TIẾT PHIÊN','rfid-detail-eyebrow'),node('h3',session.bookingIds.join(', ') || 'Phiên quét'));
        heading.append(headingText,node('span',completed?'Đã hoàn thành':'Đang scan',`rfid-status ${completed?'is-completed':'is-active'}`));
        const metrics = node('div',undefined,'rfid-detail-metrics');
        const metric = (label,value,caption) => {
          const card = node('div',undefined,'rfid-detail-metric');
          card.append(node('span',label),node('strong',value),node('small',caption));metrics.append(card);
        };
        metric('Hàng đã scan',completed?number.format(session.scannedItems ?? 0):'—',`Kế hoạch: ${number.format(session.plannedItems ?? 0)} hàng`);
        metric('Thùng đã scan',completed?number.format(session.scannedBoxes ?? 0):'—',`Kế hoạch: ${number.format(session.plannedBoxes ?? 0)} thùng`);
        metric('Hàng đã rà kim',completed?number.format(session.metalChecked ?? 0):'—',completed?'Dữ liệu đã lưu trên máy chủ':'Chưa đồng bộ');
        const details = node('div',undefined,'rfid-detail-info-grid');
        const infoCard = (label,keys) => {
          const card = node('section',undefined,'rfid-detail-card');
          const list = node('dl',undefined,'rfid-detail-fields');
          keys.forEach(key=>{
            const [,label,format] = overviewColumns.find(c=>c[0]===key);
            list.append(node('dt',label),node('dd',text(format?format(session[key]):session[key])));
          });
          card.append(node('h4',label),list);details.append(card);
        };
        infoCard('Thông tin chuyến hàng',['company','orderNos','bookingIds','vehicle','driver','note']);
        infoCard('Thông tin phiên quét',['device','startedAt','completedAt','sessionId']);
        const photosSection = node('section',undefined,'rfid-report-photos rfid-detail-card');
        const grid = node('div',undefined,'rfid-report-gallery'); const photoStatus = node('div',undefined,'rfid-detail-empty');
        photosSection.append(node('h4','Hình ảnh'),grid,photoStatus);
        content.replaceChildren(header,heading,metrics);
        if(!completed) content.append(node('p','Chưa đồng bộ dữ liệu scan. Số liệu và chi tiết RFID sẽ hiển thị sau khi phiên được hoàn thành.','rfid-detail-notice'));
        content.append(details);
        const records = node('section',undefined,'rfid-detail-card rfid-detail-records');
        const recordsHeading = node('div',undefined,'rfid-detail-records-heading');
        recordsHeading.append(node('h4',`Chi tiết RFID · ${number.format(data.total)} dòng`));
        const sizeLabel = node('label','Số dòng mỗi trang');
        const sizeSelect = node('select',undefined,'form-control');sizeSelect.name='page_size';
        [25,50,100,200,500].forEach(n=>option(sizeSelect,String(n),String(n)));
        sizeSelect.value=String(detailPageSize);
        sizeSelect.onchange=()=>{detailPageSize=Number(sizeSelect.value);open(id,1);};
        sizeLabel.append(sizeSelect);recordsHeading.append(sizeLabel);records.append(recordsHeading);
        const detailForm = node('form',undefined,'rfid-detail-filters');
        const detailInputs = {};
        for (const [key,label] of [['booking','Booking'],['po','PO'],['box','Số thùng'],['item','Mã hàng'],['market','Mã thị trường'],['color','Mã màu'],['size','Tên size'],['metal','Rà kim']]) {
          const wrap = node('label',label);
          const select = ['booking','po','box'].includes(key)?searchable(wrap,key,'Gõ để tìm '+label):node('select',undefined,'form-control');
          select.name = key;option(select,'Tất cả');
          (data.filterOptions[key] || []).forEach(v=>option(select,key==='metal'?(v==='Y'?'Đã rà kim':'Chưa rà kim'):v,v));
          if(appliedDetailFilters[key] && !(data.filterOptions[key] || []).includes(appliedDetailFilters[key])) option(select,appliedDetailFilters[key],appliedDetailFilters[key]);
          select.value=appliedDetailFilters[key] || '';detailInputs[key]=select;if(!select._choices)wrap.append(select);detailForm.append(wrap);
        }
        const applyFilters = () => {
          if(!Object.values(detailInputs).every(el=>!el.validateChoice||el.validateChoice()))return;
          detailFilters=Object.fromEntries(Object.entries(detailInputs).map(([k,el])=>[k,el.value]));open(id,1);
        };
        const filterActions = node('div',undefined,'rfid-report-actions');
        filterActions.append(iconButton('Lọc','M3 4h18l-7 8v7l-4 2v-9z',applyFilters),iconButton('Xóa lọc','M3 4h18l-7 8v4M10 21v-9M16 17l5 5m0-5-5 5',()=>{detailFilters={};open(id,1);}));
        detailForm.append(filterActions);detailForm.onsubmit=e=>{e.preventDefault();applyFilters();};records.append(detailForm);
        if(data.total) records.append(table(detailColumns,data.items),pager(data,p=>open(id,p)));
        else records.append(node('p',Object.values(appliedDetailFilters).some(Boolean)?'Không có RFID phù hợp với bộ lọc.':completed?'Phiên này chưa có dữ liệu RFID.':'Phiên đang scan — chưa có chi tiết RFID trên máy chủ.','rfid-detail-empty'));
        content.append(records,photosSection);
        gallery(id,seq,grid,photoStatus);
      } catch {if(seq===request) {error(content,()=>open(id,pageIndex));content.prepend(backButton(()=>overview(overviewPage)));}}
    }
    const imageUrl = (id,photo,thumbnail=false) => '/api/method/'+API+'photo_content?'+new URLSearchParams({session_id:id,photo_id:photo,thumbnail:thumbnail?'1':'0'});
    function viewer(id,photo) {
      const dialog=node('dialog',undefined,'rfid-report-viewer'); const close=button('Đóng',()=>dialog.close());
      const img=node('img');img.src=imageUrl(id,photo.id);img.alt=photo.fileName;
      img.onerror=()=>{img.replaceWith(node('p','Không thể tải ảnh. Ảnh có thể đã bị xóa hoặc quyền truy cập đã thay đổi.'));};
      dialog.append(close,img);root.append(dialog);dialog.onclose=()=>dialog.remove();dialog.showModal();
    }
    async function gallery(id,seq,grid,status,before) {
      status.replaceChildren(node('p','Đang tải ảnh…'));
      try {
        const data=await call('photo_list',{session_id:id,before});if(seq!==request || selected!==id)return;
        data.items.forEach(photo=>{
          const card=button('',()=>viewer(id,photo),'rfid-report-photo');
          const img=node('img');img.loading='lazy';img.src=imageUrl(id,photo.id,true);img.alt=photo.fileName;
          img.onerror=()=>{img.replaceWith(node('span','Không tải được ảnh'));};
          card.append(img,node('span',photo.fileName));grid.append(card);
        });
        status.replaceChildren();if(!grid.children.length)status.append(node('p','Chưa có ảnh.'));
        if(data.nextCursor)status.append(button('Tải thêm ảnh',()=>gallery(id,seq,grid,status,data.nextCursor)));
      } catch {if(seq===request)error(status,()=>gallery(id,seq,grid,status,before));}
    }
    filters.onsubmit=event=>{event.preventDefault();overview(1);};
    fields.company.onchange=()=>{
      fields.device.replaceChildren();option(fields.device,'Tất cả thiết bị');
      devices.filter(d=>!fields.company.value||d.company===fields.company.value).forEach(d=>option(fields.device,d.device_name||d.name,d.name));
    };
    call('options').then(data=>{
      data.companies.forEach(c=>option(fields.company,c.company_name||c.name,c.name));devices=data.devices;fields.company.onchange();
      data.statuses.forEach(s=>option(fields.status,s==='Completed'?'Đã hoàn thành':'Đang scan',s));
      data.bookings.forEach(b=>option(fields.booking,b,b));
      data.orders.forEach(po=>option(fields.po,po,po));
    }).catch(()=>{info.hidden = selected !== null; info.textContent='Không tải được bộ lọc công ty/thiết bị. Hãy tải lại trang và kiểm tra quyền báo cáo.';});
    overview();
  }
  window.RfidDeskReport={mount};
})();
