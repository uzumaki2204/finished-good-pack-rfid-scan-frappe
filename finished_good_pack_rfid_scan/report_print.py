"""Escaped print layout based on the supplied Excel summary and detail forms."""
from datetime import datetime, timedelta, timezone
from html import escape

PENDING = "Chưa đồng bộ dữ liệu scan"
VN = timezone(timedelta(hours=7))


def value(raw):
    if raw is None or raw == "":
        return "—"
    return escape(str(raw), quote=True)


def number(raw):
    return PENDING if raw is None else format(int(raw), ",").replace(",", ".")


def timestamp(raw):
    if not raw:
        return "—"
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(VN).strftime("%d/%m/%Y %H:%M:%S")


def status(raw):
    return "Đã hoàn thành" if raw == "Completed" else "Đang scan" if raw == "Active" else raw


SUMMARY = [
    ("company", "Công ty", 7), ("orderNos", "PO", 10), ("bookingIds", "Số Booking", 9),
    ("status", "Trạng thái", 7), ("vehicle", "Biển số xe", 7), ("driver", "Tài xế xe", 9),
    ("note", "Ghi chú", 9), ("startedAt", "Thời gian bắt đầu", 9), ("completedAt", "Thời gian hoàn thành", 9),
    ("scannedItems", "Số lượng hàng scan", 5), ("plannedItems", "Số lượng hàng kế hoạch", 5),
    ("metalChecked", "Số lượng rà kim", 5), ("scannedBoxes", "Số thùng scan", 5), ("plannedBoxes", "Số thùng kế hoạch", 5),
]
DETAIL = [
    ("po", "Số PO", 11), ("do", "Số DO", 13), ("item", "Mã hàng", 10), ("marketCode", "Mã thị trường", 4),
    ("marketName", "Thị trường", 6), ("colorCode", "Mã màu", 4), ("colorName", "Tên màu", 8),
    ("sizeCode", "Mã Size", 4), ("sizeName", "Tên Size", 4), ("metal", "Rà kim", 4),
    ("box", "Số thùng", 5), ("boxCode", "Code thùng", 5), ("rfid", "RFID", 17), ("scannedAt", "Thời gian scan", 10),
]


def display(key, raw):
    if key in ("orderNos", "bookingIds"):
        return value(", ".join(raw or []))
    if key in ("startedAt", "completedAt", "scannedAt"):
        return value(timestamp(raw))
    if key in ("scannedItems", "plannedItems", "metalChecked", "scannedBoxes", "plannedBoxes"):
        return number(raw)
    if key == "status":
        return value(status(raw))
    return value(raw)


def render(rows, session=None, filters=None):
    detail = session is not None
    title = "BÁO CÁO CHI TIẾT SCAN RFID LOAD CONT" if detail else "BÁO CÁO TỔNG QUAN SCAN RFID LOAD CONT"
    columns = DETAIL if detail else SUMMARY
    # Multiple bookings stay traceable without changing the single-booking Excel form.
    if detail and len(session.get("bookingIds", [])) > 1:
        columns = [("booking", "Mã Booking", 9)] + columns
    body = []
    if detail:
        body.append('<h1 class="detail-title">'+title+'</h1><table class="metadata"><tbody>')
        for groups in [
            [("Mã Booking", "bookingIds"), ("Số lượng kế hoạch", "plannedItems"), ("Scan bắt đầu", "startedAt")],
            [("Công ty", "company"), ("Số lượng scan", "scannedItems"), ("Scan hoàn thành", "completedAt")],
            [("Tài xế", "driver"), ("Số thùng kế hoạch", "plannedBoxes"), ("Trạng thái", "status")],
            [("Biển số xe", "vehicle"), ("Số thùng scan", "scannedBoxes"), ("Ghi chú", "note")],
        ]:
            body.append("<tr>"+"".join('<th>'+label+'</th><td>'+display(key, session.get(key))+'</td>' for label,key in groups)+"</tr>")
        body.append('</tbody></table>')
        if session.get("status") == "Active":
            body.append('<p class="pending">'+PENDING+'. Các lượt quét được gửi lên máy chủ khi hoàn thành phiên.</p>')
    else:
        filters = filters or {}
        body.append('<div class="filter-summary">')
        for label,key,default in [("Từ ngày","from_date",""),("Đến ngày","to_date",""),("Công ty","company","Tất cả công ty"),
                                  ("Thiết bị","device",""),("Trạng thái","status",""),("Booking","booking",""),("PO","po","")]:
            raw = filters.get(key) or default
            if raw:
                body.append('<div><b>'+label+':</b> '+value(status(raw) if key == "status" else raw)+'</div>')
        body.append('</div><h1>'+title+'</h1>')
    widths = sum(c[2] for c in columns)
    body.append('<table class="data"><colgroup>'+''.join(f'<col width="{width / widths * 100:.3f}%">' for _,_,width in columns)+'</colgroup><thead><tr>')
    body.append(''.join('<th scope="col">'+label+'</th>' for _,label,_ in columns)+'</tr></thead><tbody>')
    for row in rows:
        body.append('<tr>'+''.join('<td>'+display(key,row.get(key))+'</td>' for key,_,_ in columns)+'</tr>')
    if not rows:
        body.append(f'<tr><td colspan="{len(columns)}">Không có dữ liệu.</td></tr>')
    body.append('</tbody></table>')
    return ('<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>'+title+'</title><link rel="stylesheet" href="/assets/finished_good_pack_rfid_scan/rfid/report-print.css?v=0.1.27">'
            '<script src="/assets/finished_good_pack_rfid_scan/rfid/report-print.js?v=0.1.27" defer></script></head><body>'
            '<nav class="print-toolbar"><button id="print-report" type="button">In / Lưu PDF</button><button id="close-print" type="button">Đóng</button>'
            '<span>'+format(len(rows), ',').replace(',', '.')+' dòng · A4 ngang · Toàn bộ dữ liệu, không giới hạn ở trang đang xem</span></nav>'
            '<main>'+''.join(body)+'</main></body></html>')
