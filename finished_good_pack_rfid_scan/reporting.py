"""Read-only, role-gated Desk reporting over saved RFID data (timestamps are UTC)."""
import json
from datetime import date, datetime, time, timedelta, timezone

import frappe

from finished_good_pack_rfid_scan import photos, service

ROLES = {"System Manager", "RFID Report Manager"}
VN = timezone(timedelta(hours=7))


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
        clauses.append("EXISTS (SELECT 1 FROM `tabRFID Booking Snapshot` b WHERE b.session=s.name AND JSON_CONTAINS(JSON_EXTRACT(b.payload, '$.orderNos'), JSON_QUOTE(%(po)s)))")
        args["po"] = filters["po"]
    return " AND ".join(clauses), args


def summaries(rows):
    if not rows:
        return []
    names = tuple(row.name for row in rows)
    plans = frappe.db.sql("""SELECT session, booking_id,
        JSON_EXTRACT(payload, '$.orderNos') AS orders
        FROM `tabRFID Booking Snapshot` WHERE session IN %(names)s""", {"names": names}, as_dict=True)
    orders = {}
    for plan in plans:
        orders.setdefault(plan.session, set()).update(decode(plan.orders, []))
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
    return {"companies": frappe.get_all("Company", fields=["name", "company_name"], order_by="name"),
            "devices": frappe.get_all("Factory Device", fields=["name", "device_name", "company"], order_by="device_name")}


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
def detail(session_id, page=1):
    record = session_record(session_id)
    page = page_number(page)
    filters = {"session": record.name}
    rows = frappe.get_all(service.SCAN, filters=filters,
                          fields=["booking_id", "order_no", "do_no", "item_code", "disp_pack_num", "rfid", "is_metal_check", "scanned_at", "payload"],
                          order_by="scanned_at asc, name asc", limit_start=(page - 1) * 100, limit_page_length=100)
    items = []
    for row in rows:
        payload = decode(row.payload, {})
        # Payload is the validated, frozen plan item captured at completion.
        items.append({"booking": row.booking_id, "po": row.order_no, "do": row.do_no,
            "item": row.item_code, "marketCode": payload.get("marketCode"), "marketName": payload.get("marketName"),
            "colorCode": payload.get("colorCode"), "colorName": payload.get("colorName"),
            "sizeCode": payload.get("sizeCode"), "sizeName": payload.get("sizeName"),
            "metal": "Y" if row.is_metal_check else "N", "box": row.disp_pack_num,
            "boxCode": payload.get("usedPackNum"), "rfid": row.rfid, "scannedAt": service._iso(row.scanned_at)})
    return {"session": summaries([record])[0], "items": items,
            "total": frappe.db.count(service.SCAN, filters), "page": page, "pageSize": 100}


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
