"""Frappe-owned RFID sessions and frozen SOAP booking plans."""

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import frappe

from finished_good_pack_rfid_scan.access import approved_device, device_data
from finished_good_pack_rfid_scan.errors import RfidError
from finished_good_pack_rfid_scan.i18n import message
from finished_good_pack_rfid_scan.plan import (
    booking_delta,
    key,
    rfid_key,
    snapshot_version,
    text,
    validate_scans,
)
from finished_good_pack_rfid_scan.soap import preload_booking


SESSION = "RFID Scan Session"
SNAPSHOT = "RFID Booking Snapshot"
SCAN = "RFID Scan Detail"


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _utc_db():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat() + ("Z" if value.tzinfo is None else "")
    return str(value).replace(" ", "T") + ("Z" if "+" not in str(value) and not str(value).endswith("Z") else "")


def _hash(*parts):
    return hashlib.sha256("\x1f".join(map(text, parts)).encode("utf-8")).hexdigest()


def _booking_ids(values):
    if not isinstance(values, list) or len(values) > 100:
        raise RfidError("error.bookings_required")
    seen = set()
    output = []
    for value in values:
        if not isinstance(value, str) or len(value) > 100:
            raise RfidError("error.invalid_request")
        booking_id = text(value)
        if booking_id and booking_id.casefold() not in seen:
            seen.add(booking_id.casefold())
            output.append(booking_id)
    if not output:
        raise RfidError("error.bookings_required")
    return output


def _session(session_id, device, lock=False):
    if not isinstance(session_id, str) or not session_id:
        raise RfidError("error.session_missing", 404)
    if lock:
        frappe.db.sql("SELECT name FROM `tabRFID Scan Session` WHERE name=%s FOR UPDATE", (session_id,))
    if not frappe.db.exists(SESSION, session_id):
        raise RfidError("error.session_missing", 404)
    record = frappe.get_doc(SESSION, session_id)
    if record.company != device.company or record.status == "Deleted":
        raise RfidError("error.session_missing", 404)
    if record.device != device.name:
        raise RfidError("error.device_session", 403)
    return record


def _load_bookings(session_id):
    rows = frappe.db.get_all(SNAPSHOT, filters={"session": session_id}, fields=["payload"], order_by="creation asc")
    return [json.loads(row.payload) for row in rows]


def _load_scans(session_id):
    rows = frappe.db.get_all(SCAN, filters={"session": session_id}, fields=["payload"], order_by="scanned_at asc")
    return [json.loads(row.payload) for row in rows]


def _save_snapshot(session, booking, backfill_only=False):
    if booking.get("companyId") != session.company or not booking.get("bookingId"):
        raise RfidError("error.plan_invalid")
    identity = _hash(session.name, key(booking["bookingId"]))
    existing = frappe.db.exists(SNAPSHOT, identity)
    if existing and backfill_only:
        return
    payload = dict(booking)
    payload["planVersion"] = payload.get("planVersion") or snapshot_version(payload)
    if existing:
        record = frappe.get_doc(SNAPSHOT, identity)
        record.payload = _json(payload)
        record.plan_version = payload["planVersion"]
        record.captured_at = _utc_db()
        record.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": SNAPSHOT,
            "snapshot_key": identity,
            "session": session.name,
            "company": session.company,
            "booking_id": payload["bookingId"],
            "plan_version": payload["planVersion"],
            "captured_at": _utc_db(),
            "payload": _json(payload),
        }).insert(ignore_permissions=True)


def _update_counts(session, bookings):
    session.booking_ids_json = _json([booking["bookingId"] for booking in bookings])
    session.planned_item_count = len({
        item["finishedGoodPackDetailId"]
        for booking in bookings for item in booking.get("items", [])
        if item.get("finishedGoodPackDetailId")
    })
    session.planned_box_count = sum(int(booking.get("plannedBoxCount") or 0) for booking in bookings)
    session.save(ignore_permissions=True)


def _card(session, bookings=None, scans=None):
    bookings = bookings if bookings is not None else _load_bookings(session.name)
    scans = scans if scans is not None else _load_scans(session.name)
    planned_boxes = sum(int(booking.get("plannedBoxCount") or 0) for booking in bookings)
    scanned_boxes = len({
        (scan.get("bookingId"), scan.get("orderNo"), scan.get("doNo"), scan.get("dispPackNum"))
        for scan in scans if scan.get("dispPackNum")
    })
    warnings = [warning for booking in bookings for warning in booking.get("planningWarnings", [])]
    return {
        "sessionId": session.name,
        "sessionStatus": session.status,
        "companyId": session.company,
        "companyName": frappe.db.get_value("Company", session.company, "company_name") or session.company,
        "deviceActivationId": session.device,
        "deviceId": session.device,
        "deviceName": frappe.db.get_value("Factory Device", session.device, "device_name") or session.device,
        "vehiclePlateNumber": session.vehicle_plate_number or "",
        "driverFullName": session.driver_full_name or "",
        "note": session.note or "",
        "sessionStartedAtUtc": _iso(session.session_started_at),
        "sessionCompletedAtUtc": _iso(session.session_completed_at),
        "totalScannedCount": int(session.total_scanned_count or 0),
        "metalCheckedCount": int(session.metal_checked_count or 0),
        "crossSessionDuplicateCount": int(session.cross_session_duplicate_count or 0),
        "plannedItemCount": int(session.planned_item_count or 0),
        "plannedBoxCount": planned_boxes,
        "mappedPlannedBoxCount": sum(int(booking.get("mappedBoxCount") or 0) for booking in bookings),
        "unmappedPlannedBoxCount": sum(int(booking.get("unmappedBoxCount") or 0) for booking in bookings),
        "boxScannedCount": scanned_boxes,
        "boxTotalCount": planned_boxes,
        "hasPlanningMismatch": bool(warnings),
        "planningWarnings": warnings,
        "bookingIds": [booking["bookingId"] for booking in bookings],
        "orderNos": sorted({order for booking in bookings for order in booking.get("orderNos", [])}),
        "purchaseOrderCount": len({order for booking in bookings for order in booking.get("orderNos", [])}),
        "requiresOnlineCompletion": session.status == "Active",
        "completionWarnings": ([message("warning.cross_session_duplicate", count=session.cross_session_duplicate_count)]
                               if session.cross_session_duplicate_count else []),
    }


def _details(session):
    bookings = _load_bookings(session.name)
    scans = _load_scans(session.name)
    result = _card(session, bookings, scans)
    scan_ids = {(scan["bookingId"], scan["finishedGoodPackDetailId"]) for scan in scans}
    purchase_orders = defaultdict(lambda: {"plannedItemCount": 0, "scannedItemCount": 0, "boxes": set()})
    items = defaultdict(lambda: {"plannedItemCount": 0, "scannedItemCount": 0})
    boxes = defaultdict(lambda: {"plannedItemCount": 0, "scannedItemCount": 0, "metalCheckedCount": 0, "detailIds": []})
    for booking in bookings:
        for item in booking.get("items", []):
            item_id = item["finishedGoodPackDetailId"]
            found = (booking["bookingId"], item_id) in scan_ids
            order_key = (booking["bookingId"], item.get("orderNo", ""))
            po = purchase_orders[order_key]
            po["plannedItemCount"] += 1
            po["scannedItemCount"] += int(found)
            po["boxes"].add((item.get("doNo", ""), item.get("dispPackNum", "")))
            item_key = (booking["bookingId"], item.get("orderNo", ""), item.get("itemCode", ""), item.get("colorCode", ""), item.get("sizeCode", ""))
            item_row = items[item_key]
            item_row["plannedItemCount"] += 1
            item_row["scannedItemCount"] += int(found)
            box_key = (booking["bookingId"], item.get("orderNo", ""), item.get("doNo", ""), item.get("dispPackNum", ""))
            box = boxes[box_key]
            box["plannedItemCount"] += 1
            box["scannedItemCount"] += int(found)
            box["metalCheckedCount"] += int(found and _metal(item.get("isMetalCheck")))
            box["detailIds"].append(item_id)
    result["purchaseOrders"] = [
        {"bookingId": booking_id, "orderNo": order_no,
         "plannedItemCount": row["plannedItemCount"], "scannedItemCount": row["scannedItemCount"],
         "boxCount": len(row["boxes"])}
        for (booking_id, order_no), row in sorted(purchase_orders.items())
    ]
    result["items"] = [
        {"bookingId": booking_id, "orderNo": order_no, "itemCode": item_code,
         "colorCode": color_code, "sizeCode": size_code, **row}
        for (booking_id, order_no, item_code, color_code, size_code), row in sorted(items.items())
    ]
    result["boxes"] = [
        {"bookingId": booking_id, "orderNo": order_no, "doNo": do_no, "dispPackNum": box_no,
         "plannedItemCount": row["plannedItemCount"], "scannedItemCount": row["scannedItemCount"],
         "metalCheckedCount": row["metalCheckedCount"],
         "isCompleted": row["plannedItemCount"] == row["scannedItemCount"],
         "hasMissingMetalCheck": row["metalCheckedCount"] < row["scannedItemCount"],
         "finishedGoodPackDetailIds": row["detailIds"]}
        for (booking_id, order_no, do_no, box_no), row in sorted(boxes.items())
    ]
    result["scannedItems"] = scans
    result["preloadedBookings"] = bookings
    return result


def _metal(value):
    return key(value) in ("1", "TRUE", "YES", "Y", "PASS", "ĐÃ RÀ KIM")


def device_check(device_id):
    return device_data(approved_device(device_id))


def preview_conflicts(device_id, booking_ids):
    device = approved_device(device_id)
    requested = _booking_ids(booking_ids)
    wanted = {key(value) for value in requested}
    sessions = frappe.db.get_all(SESSION, filters={"company": device.company, "status": "Active"}, fields=["name"], order_by="session_started_at desc")
    conflicts = []
    for row in sessions:
        session = frappe.get_doc(SESSION, row.name)
        matching = [value for value in json.loads(session.booking_ids_json or "[]") if key(value) in wanted]
        if matching:
            conflicts.append({
                "session": _card(session), "matchingBookingIds": matching,
                "canResumeOnCurrentDevice": session.device == device.name,
                "resumeBlockedReason": "" if session.device == device.name else message("error.device_session"),
            })
    return {"requestedBookingIds": requested, "sessions": conflicts}


def start_session(device_id, booking_ids, vehicle="", driver="", confirm_conflicts=False):
    device = approved_device(device_id)
    requested = _booking_ids(booking_ids)
    preloaded = []
    seen = set()
    for booking_id in requested:
        booking = preload_booking(device.company, booking_id)
        if key(booking["bookingId"]) not in seen:
            seen.add(key(booking["bookingId"]))
            preloaded.append(booking)
    frappe.db.sql("SELECT name FROM `tabCompany` WHERE name=%s FOR UPDATE", (device.company,))
    conflicts = preview_conflicts(device_id, [row["bookingId"] for row in preloaded])["sessions"]
    if conflicts and not confirm_conflicts:
        raise RfidError("error.session_conflict", 409)
    session_id = str(uuid.uuid4())
    session = frappe.get_doc({
        "doctype": SESSION, "session_id": session_id,
        "company": device.company, "device": device.name, "status": "Active",
        "vehicle_plate_number": text(vehicle)[:100], "driver_full_name": text(driver)[:140],
        "session_started_at": _utc_db(), "booking_ids_json": _json([row["bookingId"] for row in preloaded]),
        "planned_item_count": 0, "planned_box_count": 0,
    }).insert(ignore_permissions=True)
    for booking in preloaded:
        _save_snapshot(session, booking)
    _update_counts(session, preloaded)
    return {"session": _details(session), "preloadedBookings": preloaded}


def create_session(device_id, vehicle="", driver=""):
    device = approved_device(device_id)
    session_id = str(uuid.uuid4())
    session = frappe.get_doc({
        "doctype": SESSION, "session_id": session_id,
        "company": device.company, "device": device.name, "status": "Active",
        "vehicle_plate_number": text(vehicle)[:100], "driver_full_name": text(driver)[:140],
        "session_started_at": _utc_db(), "booking_ids_json": "[]",
    }).insert(ignore_permissions=True)
    return _details(session)


def active_sessions(device_id):
    device = approved_device(device_id)
    rows = frappe.db.get_all(SESSION, filters={"company": device.company, "device": device.name, "status": "Active"}, fields=["name"], order_by="session_started_at desc")
    return [_card(frappe.get_doc(SESSION, row.name)) for row in rows]


def history(device_id, status="Completed", page_index=1):
    device = approved_device(device_id)
    page_index = max(1, int(page_index or 1))
    filters = {"company": device.company, "device": device.name,
               "status": status if status in ("Active", "Completed") else "Completed"}
    total = frappe.db.count(SESSION, filters=filters)
    rows = frappe.db.get_all(SESSION, filters=filters, fields=["name"], order_by="session_completed_at desc, session_started_at desc", limit_start=(page_index - 1) * 5, limit_page_length=5)
    return {"items": [_card(frappe.get_doc(SESSION, row.name)) for row in rows], "totalCount": total,
            "pageIndex": page_index, "pageSize": 5, "totalPages": (total + 4) // 5}


def get_session(device_id, session_id):
    device = approved_device(device_id)
    return _details(_session(session_id, device))


def preload(device_id, booking_id, session_id=None):
    device = approved_device(device_id)
    session = _session(session_id, device, lock=True) if session_id else None
    if session and session.status != "Active":
        raise RfidError("error.session_inactive")
    booking = preload_booking(device.company, booking_id)
    if session:
        _save_snapshot(session, booking)
        _update_counts(session, _load_bookings(session.name))
    return booking


def refresh_delta(device_id, session_id, booking_id):
    device = approved_device(device_id)
    session = _session(session_id, device, lock=True)
    if session.status != "Active":
        raise RfidError("error.session_inactive")
    current = _load_bookings(session_id)
    old = next((row for row in current if key(row["bookingId"]) == key(booking_id)
                or key(row.get("displayBookingId")) == key(booking_id)), None)
    if not old:
        raise RfidError("error.booking_not_in_session")
    booking = preload_booking(device.company, old["bookingId"])
    delta = booking_delta(old, booking)
    _save_snapshot(session, booking)
    _update_counts(session, _load_bookings(session.name))
    return {"sessionId": session_id, "bookingId": booking["bookingId"],
            "displayBookingId": booking["displayBookingId"], **delta,
            "booking": booking, "session": _details(session)}


def rehydrate(device_id, session_id):
    device = approved_device(device_id)
    session = _session(session_id, device, lock=True)
    if session.status != "Active":
        raise RfidError("error.session_inactive")
    bookings = _load_bookings(session_id)
    if not bookings:
        ids = json.loads(session.booking_ids_json or "[]")
        if not ids:
            raise RfidError("error.rehydrate_invalid")
        bookings = [preload_booking(device.company, booking_id) for booking_id in ids]
        for booking in bookings:
            _save_snapshot(session, booking)
        _update_counts(session, bookings)
    return {"sessionId": session_id, "session": _details(session), "bookingCount": len(bookings),
            "plannedItemCount": sum(len(row.get("items", [])) for row in bookings),
            "plannedBoxCount": sum(int(row.get("plannedBoxCount") or 0) for row in bookings)}


def complete(device_id, session_id, vehicle, driver, note, scans):
    device = approved_device(device_id)
    session = _session(session_id, device, lock=True)
    if session.status == "Completed":
        return _details(session)
    if session.status != "Active":
        raise RfidError("error.session_inactive")
    if not text(vehicle) or not text(driver):
        raise RfidError("error.session_header")
    bookings = _load_bookings(session_id)
    if not bookings:
        raise RfidError("error.plan_missing")
    resolved = validate_scans(scans, bookings)
    # Serialize duplicate counting for sessions in the same company.
    frappe.db.sql("SELECT name FROM `tabCompany` WHERE name=%s FOR UPDATE", (device.company,))
    duplicate_count = 0
    for scan in resolved:
        normalized_rfid = rfid_key(scan["rfid"])
        if frappe.db.exists(SCAN, {"company": device.company, "normalized_rfid": normalized_rfid}):
            duplicate_count += 1
        detail_id = scan["finishedGoodPackDetailId"]
        frappe.get_doc({
            "doctype": SCAN, "scan_key": _hash(session_id, scan["bookingId"], detail_id),
            "session": session_id, "company": device.company, "device": device.name,
            "detail_id": detail_id, "rfid": scan["rfid"], "normalized_rfid": normalized_rfid,
            "scanned_at": datetime.fromisoformat(scan["scannedAtUtc"]).strftime("%Y-%m-%d %H:%M:%S.%f"),
            "booking_id": scan["bookingId"], "order_no": scan.get("orderNo", ""),
            "do_no": scan.get("doNo", ""), "item_code": scan.get("itemCode", ""),
            "disp_pack_num": scan.get("dispPackNum", ""),
            "is_metal_check": int(_metal(scan.get("isMetalCheck"))),
            "payload": _json(scan),
        }).insert(ignore_permissions=True)
    session.vehicle_plate_number = text(vehicle)[:100]
    session.driver_full_name = text(driver)[:140]
    session.note = text(note)
    session.status = "Completed"
    session.session_completed_at = _utc_db()
    session.total_scanned_count = len(resolved)
    session.metal_checked_count = sum(_metal(scan.get("isMetalCheck")) for scan in resolved)
    session.cross_session_duplicate_count = duplicate_count
    session.completion_hash = _hash(_json(sorted(resolved, key=lambda row: row["finishedGoodPackDetailId"])))
    session.save(ignore_permissions=True)
    return _details(session)


def delete_session(device_id, session_id):
    device = approved_device(device_id)
    session = _session(session_id, device, lock=True)
    session.status = "Deleted"
    session.deleted_at = _utc_db()
    session.save(ignore_permissions=True)
    return {"sessionId": session_id, "companyId": device.company, "sessionStatus": "Deleted",
            "deletedAtUtc": _iso(session.deleted_at)}
