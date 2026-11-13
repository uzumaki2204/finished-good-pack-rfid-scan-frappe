"""Session-scoped private photos; every request rechecks the tablet's authority."""
import hashlib
from pathlib import PurePosixPath
from uuid import UUID

import frappe

from finished_good_pack_rfid_scan import service
from finished_good_pack_rfid_scan.access import approved_device
from finished_good_pack_rfid_scan.errors import RfidError
from finished_good_pack_rfid_scan.image_processing import optimize, MAX_BYTES

DOCTYPE = "RFID Session Photo"


def authorize(device_id, session_id, lock=False):
    device = approved_device(device_id)
    if not isinstance(session_id, str) or not session_id or not frappe.db.exists(service.SESSION, session_id):
        raise RfidError("error.session_missing", 404)
    if lock:
        frappe.db.sql("SELECT name FROM `tabRFID Scan Session` WHERE name=%s FOR UPDATE", (session_id,))
    session = frappe.get_doc(service.SESSION, session_id)
    if session.company != device.company or session.status == "Deleted":
        raise RfidError("error.session_missing", 404)
    if session.status not in ("Active", "Completed"):
        raise RfidError("error.session_inactive", 403)
    return session, device


def public_photo(row):
    return {"id": row.name, "fileName": row.original_name, "width": row.width,
            "height": row.height, "size": row.byte_size, "uploadedAt": str(row.creation)}


def list_photos(device_id, session_id, before=None):
    session, device = authorize(device_id, session_id)
    filters = {"session": session_id, "deleted": 0}
    if before:
        filters["name"] = ["<", str(before)]
    rows = frappe.get_all(DOCTYPE, filters=filters,
                          fields=["name", "original_name", "width", "height", "byte_size", "creation", "device"],
                          order_by="name desc", limit_page_length=25)
    return {"items": [{**public_photo(row), "canDelete": device.name in (session.device, row.device)} for row in rows[:24]],
            "nextCursor": rows[23].name if len(rows) > 24 else None}


def upload(device_id, session_id, request_id, uploaded):
    # Lock the session to serialize retries, deletion and completion across requests.
    session, device = authorize(device_id, session_id, lock=True)
    try:
        request_id = str(UUID(str(request_id)))
    except (ValueError, TypeError, AttributeError):
        raise RfidError("error.invalid_request") from None
    request_key = hashlib.sha256(f"{session.name}|{request_id}".encode()).hexdigest()
    existing = frappe.db.get_value(DOCTYPE, {"request_key": request_key}, "name")
    if existing:
        photo = frappe.get_doc(DOCTYPE, existing)
        if photo.deleted:
            raise RfidError("error.photo_deleted", 409)
        return public_photo(photo)
    if uploaded is None:
        raise RfidError("error.photo_format")
    content = uploaded.stream.read(MAX_BYTES + 1)
    full, thumbnail, width, height = optimize(content)
    original_name = PurePosixPath((uploaded.filename or "image").replace("\\", "/")).name[:140]
    photo = frappe.get_doc({"doctype": DOCTYPE, "session": session.name, "company": device.company,
                           "device": device.name, "request_key": request_key, "original_name": original_name,
                           "width": width, "height": height, "byte_size": len(full), "deleted": 0,
                           "owner": "Administrator"}).insert(ignore_permissions=True)
    for field, data, suffix in (("image_file", full, "image"), ("thumbnail_file", thumbnail, "thumb")):
        file = frappe.get_doc({"doctype": "File", "file_name": f"{photo.name}-{suffix}.webp",
                               "content": data, "is_private": 1, "owner": "Administrator",
                               "attached_to_doctype": DOCTYPE, "attached_to_name": photo.name})
        file.insert(ignore_permissions=True)
        photo.set(field, file.name)
    photo.save(ignore_permissions=True)
    return public_photo(photo)


def get_photo(device_id, session_id, photo_id, lock=False):
    authorize(device_id, session_id, lock=lock)
    if not photo_id or not frappe.db.exists(DOCTYPE, photo_id):
        raise RfidError("error.photo_missing", 404)
    photo = frappe.get_doc(DOCTYPE, photo_id)
    if photo.session != session_id or photo.deleted:
        raise RfidError("error.photo_missing", 404)
    return photo


def read(device_id, session_id, photo_id, thumbnail=False):
    photo = get_photo(device_id, session_id, photo_id)
    file = frappe.get_doc("File", photo.thumbnail_file if thumbnail else photo.image_file)
    if not file.is_private or file.attached_to_doctype != DOCTYPE or file.attached_to_name != photo.name:
        raise RfidError("error.photo_missing", 404)
    return file.get_content()


def delete(device_id, session_id, photo_id):
    # Keep the request key as a tombstone: a delayed upload retry cannot recreate a deleted photo.
    session, device = authorize(device_id, session_id, lock=True)
    if not photo_id or not frappe.db.exists(DOCTYPE, photo_id):
        raise RfidError("error.photo_missing", 404)
    photo = frappe.get_doc(DOCTYPE, photo_id)
    if photo.session != session_id:
        raise RfidError("error.photo_missing", 404)
    if device.name not in (session.device, photo.device):
        raise RfidError("error.device_session", 403)
    if not photo.deleted:
        for file_id in (photo.image_file, photo.thumbnail_file):
            if file_id:
                file = frappe.get_doc("File", file_id)
                if file.attached_to_doctype != DOCTYPE or file.attached_to_name != photo.name:
                    raise RfidError("error.photo_missing", 404)
                frappe.delete_doc("File", file_id, ignore_permissions=True)
        photo.image_file = photo.thumbnail_file = None
        photo.deleted = 1
        photo.save(ignore_permissions=True)
    return {"id": photo.name, "deleted": True}
