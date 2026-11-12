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
      const wrap = node('label',label); const el = node(type === 'select' ? 'select':'input', undefined, 'form-control');
      if (type !== 'select') el.type = type;
      el.name = key; el.value = value; wrap.append(el); filters.append(wrap); fields[key] = el; return el;
    };
    input('from_date','Từ ngày','date',now.slice(0,8)+'01'); input('to_date','Đến ngày','date',now);
    input('company','Công ty','select'); input('device','Thiết bị','select'); input('status','Trạng thái','select');
    input('booking','Booking'); input('po','PO');
    const option = (select,label,value='') => {const el = node('option',label);el.value = value;select.append(el);};
    option(fields.company,'Tất cả công ty'); option(fields.device,'Tất cả thiết bị');
    option(fields.status,'Tất cả trạng thái'); option(fields.status,'Đang scan','Active'); option(fields.status,'Đã hoàn thành','Completed');
    const load = refreshButton(() => overview(1));
    const print = printButton(() => {}); print.disabled = true;
    const filterActions = node('div', undefined, 'rfid-report-filter-actions');
    filterActions.append(load,print); filters.append(filterActions);
    const info = node('p','','text-danger'); info.hidden = true;
    const content = node('section'); root.append(filters,info,content);
    let request = 0, selected = null, overviewPage = 1, devices = [];
    function printReport(args) {
      window.open('/api/method/' + API + 'print_report?' + new URLSearchParams(args), '_blank', 'noopener');
    }
    function error(target, action) {target.replaceChildren(node('p','Không thể tải dữ liệu. Vui lòng kiểm tra quyền truy cập hoặc thử lại.','text-danger'),button('Thử lại',action));}
    async function overview(pageIndex=1) {
      const seq = ++request; selected = null; overviewPage = pageIndex; setHeading(false);
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
      const seq = ++request; selected = id; setHeading(true); filters.hidden = true; info.hidden = true;
      content.replaceChildren(node('p','Đang tải chi tiết…'));
      try {
        const data = await call('detail',{session_id:id,page:pageIndex}); if(seq !== request) return;
        const header = node('div',undefined,'rfid-report-actions'); header.append(backButton(()=>overview(overviewPage)),refreshButton(()=>open(id,pageIndex)),printButton(()=>printReport({session_id:id})));
        const title = node('h3',`Chi tiết phiên · ${data.session.bookingIds.join(', ')}`);
        const summary = node('dl',undefined,'rfid-report-summary');
        overviewColumns.forEach(([key,label,format])=>{summary.append(node('dt',label),node('dd',text(format?format(data.session[key]):data.session[key])));});
        const photosSection = node('section',undefined,'rfid-report-photos');
        const grid = node('div',undefined,'rfid-report-gallery'); const photoStatus = node('div');
        photosSection.append(node('h4','Hình ảnh'),grid,photoStatus);
        content.replaceChildren(header,title,summary);
        if(data.session.status === 'Active') content.append(node('p',pending + '. Các lượt quét được gửi lên máy chủ khi hoàn thành phiên.','alert alert-info'));
        content.append(node('h4','Chi tiết RFID'),table(detailColumns,data.items),pager(data,p=>open(id,p)),photosSection);
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
    }).catch(()=>{info.hidden = selected !== null; info.textContent='Không tải được bộ lọc công ty/thiết bị. Hãy tải lại trang và kiểm tra quyền báo cáo.';});
    overview();
  }
  window.RfidDeskReport={mount};
})();
