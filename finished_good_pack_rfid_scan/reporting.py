"""Read-only, role-gated Desk reporting over saved RFID data (timestamps are UTC)."""
import json
from datetime import date, datetime, time, timedelta, timezone

import frappe

from finished_good_pack_rfid_scan import photos, service

ROLES = {"System Manager", "RFID Report Manager"}
VN = timezone(timedelta(hours=7))


def stored_orders_sql(payload="payload"):
    # Older/imported snapshots may omit orderNos but still contain PO-level summaries.
    return "JSON_MERGE_PRESERVE(" + ", ".join(
        f"COALESCE(JSON_EXTRACT({payload}, '$.{path}'), JSON_ARRAY())"
        for path in ("orderNos", "items[*].orderNo", "summaryRows[*].orderNo")
    ) + ")"


def stored_orders(value):
    return {str(po).strip() for po in decode(value, []) if po is not None and str(po).strip()}



def can_open():
    return frappe.session.user != "Guest" and bool(ROLES.intersection(frappe.get_roles()))


def authorize():
    if not can_open():
        frappe.throw("Bạn không có quyền xem báo cáo RFID.", frappe.PermissionError)


def session_record(session_id):
    authorize()
    if not session_id or not frappe.db.exists(service.SESSION, session_id):
        frappe.throw("Không tìm thấy phiên.", frappe.DoesNotExistError)
    record = frappe.get_doc(service.SESSION, session_id)
    if record.status not in ("Active", "Completed"):
        frappe.throw("Không tìm thấy phiên.", frappe.DoesNotExistError)
    return record


def page_number(value):
    try:
        result = int(value)
        if result < 1 or str(result) != str(value):
            raise ValueError
        return result
    except (ValueError, TypeError):
        frappe.throw("Trang không hợp lệ.", frappe.ValidationError)


def date_bounds(from_date=None, to_date=None):
    today = datetime.now(VN).date()
    try:
        start = date.fromisoformat(from_date) if from_date else today.replace(day=1)
        end = date.fromisoformat(to_date) if to_date else today
        if end < start:
            raise ValueError
        return tuple(datetime.combine(day, time.min, VN).astimezone(timezone.utc).replace(tzinfo=None)
                     for day in (start, end + timedelta(days=1)))
    except (ValueError, TypeError, OverflowError):
        frappe.throw("Khoảng ngày không hợp lệ.", frappe.ValidationError)


def decode(value, default):
    return json.loads(value) if value else default


def where_clause(filters):
    start, end = date_bounds(filters.get("from_date"), filters.get("to_date"))
    clauses = ["s.status IN ('Active', 'Completed')", "s.session_started_at >= %(start)s", "s.session_started_at < %(end)s"]
    args = {"start": start, "end": end}
    for field in ("company", "device", "status"):
        value = filters.get(field)
        if value:
            if field == "status" and value not in ("Active", "Completed"):
                frappe.throw("Trạng thái không hợp lệ.", frappe.ValidationError)
            clauses.append(f"s.{field} = %({field})s")
            args[field] = value
    if filters.get("booking"):
        clauses.append("EXISTS (SELECT 1 FROM `tabRFID Booking Snapshot` b WHERE b.session=s.name AND b.booking_id=%(booking)s)")
        args["booking"] = filters["booking"]
    if filters.get("po"):
        clauses.append(f"(EXISTS (SELECT 1 FROM `tabRFID Booking Snapshot` b WHERE b.session=s.name AND JSON_CONTAINS({stored_orders_sql('b.payload')}, JSON_QUOTE(%(po)s))) OR EXISTS (SELECT 1 FROM `tabRFID Scan Detail` d WHERE d.session=s.name AND d.order_no=%(po)s))")
        args["po"] = filters["po"]
    return " AND ".join(clauses), args


def summaries(rows):
    if not rows:
        return []
    names = tuple(row.name for row in rows)
    plans = frappe.db.sql(f"""SELECT session, booking_id,
        {stored_orders_sql()} AS orders
        FROM `tabRFID Booking Snapshot` WHERE session IN %(names)s
        UNION SELECT session, booking_id, JSON_ARRAY(order_no) AS orders
        FROM `tabRFID Scan Detail` WHERE session IN %(names)s AND COALESCE(order_no, '') != ''""", {"names": names}, as_dict=True)
    orders = {}
    for plan in plans:
        orders.setdefault(plan.session, set()).update(stored_orders(plan.orders))
    # GROUP BY the full tuple; concatenating identifiers can collide or drop NULLs.
    boxes = frappe.db.sql("""SELECT session, COUNT(*) AS n FROM (
        SELECT session, booking_id, order_no, do_no, disp_pack_num
        FROM `tabRFID Scan Detail` WHERE session IN %(names)s AND COALESCE(disp_pack_num, '') != ''
        GROUP BY session, booking_id, order_no, do_no, disp_pack_num
        ) distinct_boxes GROUP BY session""", {"names": names}, as_dict=True)
    counts = {row.session: row.n for row in boxes}
    companies = {row.name: row.company_name for row in frappe.get_all("Company", fields=["name", "company_name"])}
    devices = {row.name: row.device_name for row in frappe.get_all("Factory Device", filters={"name": ["in", list({row.device for row in rows})]}, fields=["name", "device_name"])}
    result = []
    for row in rows:
        completed = row.status == "Completed"
        result.append({"sessionId": row.name, "company": companies.get(row.company) or row.company,
            "companyId": row.company, "device": devices.get(row.device) or row.device,
            "deviceId": row.device, "status": row.status,
            "bookingIds": decode(row.booking_ids_json, []), "orderNos": sorted(orders.get(row.name, [])),
            "vehicle": row.vehicle_plate_number, "driver": row.driver_full_name, "note": row.note,
            "startedAt": service._iso(row.session_started_at), "completedAt": service._iso(row.session_completed_at),
            "plannedItems": row.planned_item_count, "plannedBoxes": row.planned_box_count,
            "scannedItems": row.total_scanned_count if completed else None,
            "metalChecked": row.metal_checked_count if completed else None,
            "scannedBoxes": counts.get(row.name, 0) if completed else None})
    return result


@frappe.whitelist(methods=["GET"])
def options():
    authorize()
    sessions = frappe.db.sql("""SELECT DISTINCT company, device, status
        FROM `tabRFID Scan Session` WHERE status IN ('Active', 'Completed')""", as_dict=True)
    company_ids = sorted({row.company for row in sessions if row.company})
    device_ids = sorted({row.device for row in sessions if row.device})
    snapshots = frappe.db.sql(f"""SELECT DISTINCT b.booking_id, {stored_orders_sql('b.payload')} AS orders
        FROM `tabRFID Booking Snapshot` b INNER JOIN `tabRFID Scan Session` s ON s.name=b.session
        WHERE s.status IN ('Active', 'Completed')
        UNION SELECT DISTINCT d.booking_id, JSON_ARRAY(d.order_no) AS orders
        FROM `tabRFID Scan Detail` d INNER JOIN `tabRFID Scan Session` s ON s.name=d.session
        WHERE s.status IN ('Active', 'Completed') AND COALESCE(d.order_no, '') != ''""", as_dict=True)
    return {
        "companies": frappe.get_all("Company", filters={"name": ["in", company_ids]},
            fields=["name", "company_name"], order_by="company_name") if company_ids else [],
        "devices": frappe.get_all("Factory Device", filters={"name": ["in", device_ids]},
            fields=["name", "device_name", "company"], order_by="device_name") if device_ids else [],
        "statuses": sorted({row.status for row in sessions}),
        "bookings": sorted({row.booking_id for row in snapshots if row.booking_id}),
        "orders": sorted({po for row in snapshots for po in stored_orders(row.orders)}),
    }


@frappe.whitelist(methods=["GET"])
def overview(from_date=None, to_date=None, company=None, device=None, status=None, booking=None, po=None, page=1):
    authorize()
    page = page_number(page)
    where, args = where_clause(dict(from_date=from_date, to_date=to_date, company=company,
                                   device=device, status=status, booking=booking, po=po))
    total = frappe.db.sql(f"SELECT COUNT(*) FROM `tabRFID Scan Session` s WHERE {where}", args)[0][0]
    args.update(limit=50, offset=(page - 1) * 50)
    rows = frappe.db.sql(f"SELECT s.* FROM `tabRFID Scan Session` s WHERE {where} ORDER BY s.session_started_at DESC, s.name DESC LIMIT %(limit)s OFFSET %(offset)s", args, as_dict=True)
    return {"items": summaries(rows), "total": total, "page": page, "pageSize": 50}


@frappe.whitelist(methods=["GET"])
def detail(session_id, page=1, box=None, item=None, market=None, color=None, size=None, metal=None, booking=None, po=None, page_size=100):
    record = session_record(session_id)
    page_size = page_number(page_size)
    if page_size not in (25, 50, 100, 200, 500):
        frappe.throw("Số dòng mỗi trang không hợp lệ.", frappe.ValidationError)
    page = page_number(page)
    filters = dict(box=box, item=item, market=market, color=color, size=size, metal=metal, booking=booking, po=po)
    where, args = detail_where(record.name, filters)
    total = frappe.db.sql(f"SELECT COUNT(*) FROM `tabRFID Scan Detail` WHERE {where}", args)[0][0] if any(v not in (None, "") for v in filters.values()) else frappe.db.count(service.SCAN, {"session": record.name})
    expressions = ", ".join(f"{expr} AS `{key}`" for key, expr in DETAIL_FILTERS.items())
    choices = frappe.db.sql(f"SELECT DISTINCT {expressions} FROM `tabRFID Scan Detail` WHERE session=%s", (record.name,), as_dict=True)
    return {"session": summaries([record])[0], "items": scan_items(record.name, (page - 1) * page_size, page_size, filters),
            "total": total, "page": page, "pageSize": page_size,
            "filterOptions": {key: sorted({str(row[key]) for row in choices if row[key] not in (None, "")}) for key in DETAIL_FILTERS}}


DETAIL_FILTERS = {
    "booking": "booking_id",
    "po": "order_no",
    "box": "disp_pack_num",
    "item": "SUBSTRING(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.sampleCode')), 'null'), 3)",
    "market": "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.marketCode')), 'null')",
    "color": "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.colorCode')), 'null')",
    "size": "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.sizeName')), 'null')",
    "metal": "CASE WHEN is_metal_check=1 THEN 'Y' ELSE 'N' END",
}


def detail_where(session_id, filters=None):
    clauses, args = ["session=%(session)s"], {"session": session_id}
    for field, value in (filters or {}).items():
        if field not in DETAIL_FILTERS or value in (None, ""):
            continue
        if field == "metal" and value not in ("Y", "N"):
            frappe.throw("Trạng thái rà kim không hợp lệ.", frappe.ValidationError)
        clauses.append(f"{DETAIL_FILTERS[field]}=%({field})s")
        args[field] = str(value)
    return " AND ".join(clauses), args


def scan_items(session_id, offset=0, limit=100, filters=None):
    """Use the same frozen scan mapping for Desk pages and full printed reports."""
    fields = ["booking_id", "order_no", "do_no", "item_code", "disp_pack_num", "rfid", "is_metal_check", "scanned_at", "payload"]
    if any(v not in (None, "") for v in (filters or {}).values()):
        where, args = detail_where(session_id, filters)
        args.update(offset=offset, limit=limit)
        rows = frappe.db.sql(f"SELECT {', '.join(fields)} FROM `tabRFID Scan Detail` WHERE {where} ORDER BY scanned_at asc, name asc LIMIT %(limit)s OFFSET %(offset)s", args, as_dict=True)
    else:
        rows = frappe.get_all(service.SCAN, filters={"session": session_id}, fields=fields,
                             order_by="scanned_at asc, name asc", limit_start=offset, limit_page_length=limit)
    items = []
    for row in rows:
        payload = decode(row.payload, {})
        items.append({"booking": row.booking_id, "po": row.order_no, "do": row.do_no,
            "item": (payload.get("sampleCode") or "")[2:], "marketCode": payload.get("marketCode"), "marketName": payload.get("marketName"),
            "colorCode": payload.get("colorCode"), "colorName": payload.get("colorName"),
            "sizeCode": payload.get("sizeCode"), "sizeName": payload.get("sizeName"),
            "metal": "Y" if row.is_metal_check else "N", "box": row.disp_pack_num,
            "boxCode": payload.get("setCode"), "rfid": row.rfid, "scannedAt": service._iso(row.scanned_at)})
    return items


@frappe.whitelist(methods=["GET"])
def photo_list(session_id, before=None):
    session_record(session_id)
    filters = {"session": session_id, "deleted": 0}
    if before:
        filters["name"] = ["<", str(before)]
    rows = frappe.get_all(photos.DOCTYPE, filters=filters,
        fields=["name", "original_name", "width", "height", "byte_size", "creation"],
        order_by="name desc", limit_page_length=25)
    return {"items": [photos.public_photo(row) for row in rows[:24]],
            "nextCursor": rows[23].name if len(rows) > 24 else None}


@frappe.whitelist(methods=["GET"])
def photo_content(session_id, photo_id, thumbnail=None):
    session_record(session_id)
    photo = frappe.get_doc(photos.DOCTYPE, photo_id)
    if photo.session != session_id or photo.deleted:
        frappe.throw("Không tìm thấy ảnh.", frappe.DoesNotExistError)
    file = frappe.get_doc("File", photo.thumbnail_file if str(thumbnail) == "1" else photo.image_file)
    if not file.is_private or file.attached_to_doctype != photos.DOCTYPE or file.attached_to_name != photo.name:
        frappe.throw("Không tìm thấy ảnh.", frappe.DoesNotExistError)
    from werkzeug.wrappers import Response

    return Response(file.get_content(), mimetype="image/webp", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": 'inline; filename="rfid-photo.webp"'})


@frappe.whitelist(methods=["GET"])
def print_report(session_id=None, from_date=None, to_date=None, company=None, device=None,
                 status=None, booking=None, po=None, box=None, item=None, market=None, color=None, size=None, metal=None):
    """Authenticated print preview containing every matching row, never just the current page."""
    authorize()
    from finished_good_pack_rfid_scan.report_print import render
    from werkzeug.wrappers import Response

    filters = dict(from_date=from_date, to_date=to_date, company=company, device=device,
                   status=status, booking=booking, po=po)
    if session_id:
        record = session_record(session_id)
        summary = summaries([record])[0]
        rows = []
        offset = 0
        while True:
            batch = scan_items(record.name, offset, 500, dict(box=box, item=item, market=market, color=color, size=size, metal=metal, booking=booking, po=po))
            rows.extend(batch)
            if len(batch) < 500:
                break
            offset += 500
        html = render(rows, session=summary)
    else:
        where, args = where_clause(filters)
        records = frappe.db.sql(f"SELECT s.* FROM `tabRFID Scan Session` s WHERE {where} ORDER BY s.session_started_at DESC, s.name DESC", args, as_dict=True)
        rows = []
        for offset in range(0, len(records), 50):
            rows.extend(summaries(records[offset:offset + 50]))
        start, end = date_bounds(from_date, to_date)
        filters["from_date"] = (start.replace(tzinfo=timezone.utc).astimezone(VN)).strftime("%d/%m/%Y")
        filters["to_date"] = ((end.replace(tzinfo=timezone.utc).astimezone(VN)) - timedelta(days=1)).strftime("%d/%m/%Y")
        if company:
            filters["company"] = frappe.db.get_value("Company", company, "company_name") or company
        if device:
            filters["device"] = frappe.db.get_value("Factory Device", device, "device_name") or device
        html = render(rows, filters=filters)
    return Response(html, mimetype="text/html", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'self'",
        "Referrer-Policy": "same-origin"})
