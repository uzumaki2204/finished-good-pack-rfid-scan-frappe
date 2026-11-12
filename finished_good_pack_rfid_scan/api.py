"""Tablet API. Every operation resolves the approved Frappe device again."""

import traceback

import frappe

from finished_good_pack_rfid_scan import service, photos
from finished_good_pack_rfid_scan.errors import RfidError
from finished_good_pack_rfid_scan.i18n import message


READ = {
    "photos": lambda d: photos.list_photos(_device(d), d.get("sessionId"), d.get("before")),
    "device_check": lambda d: service.device_check(_device(d)),
    "active": lambda d: service.active_sessions(_device(d)),
    "history": lambda d: service.history(_device(d), d.get("status", "Completed"), d.get("pageIndex", 1)),
    "session": lambda d: service.get_session(_device(d), d.get("sessionId")),
    "preview_conflicts": lambda d: service.preview_conflicts(_device(d), _array(d.get("bookingIds"))),
}
WRITE = {
    "delete_photo": lambda d: photos.delete(_device(d), d.get("sessionId"), d.get("photoId")),
    "start": lambda d: service.start_session(_device(d), d.get("bookingIds"), d.get("vehiclePlateNumber"),
                                             d.get("driverFullName"), d.get("confirmConflicts") is True),
    "preload": lambda d: service.preload(_device(d), d.get("bookingId"), d.get("sessionId")),
    "refresh_optimized": lambda d: service.refresh_optimized(_device(d), d.get("sessionId"), d.get("bookingId"), d.get("mode", "light"), d.get("planVersion")),
    "refresh_delta": lambda d: service.refresh_delta(_device(d), d.get("sessionId"), d.get("bookingId")),
    "rehydrate": lambda d: service.rehydrate(_device(d), d.get("sessionId")),
    "complete": lambda d: service.complete(_device(d), d.get("sessionId"), d.get("vehiclePlateNumber"),
                                            d.get("driverFullName"), d.get("note"), d.get("scans")),
    "delete": lambda d: service.delete_session(_device(d), d.get("sessionId")),
}
SUCCESS = {
    "device_check": "success.device_ready", "start": "success.session_started",
    "refresh_delta": "success.booking_refreshed", "rehydrate": "success.plan_restored",
    "complete": "success.session_completed", "delete": "success.session_deleted",
}


def _device(data):
    return data.get("deviceId") or data.get("deviceActivationId") or data.get("id")


def _array(value):
    if isinstance(value, str):
        import json

        value = json.loads(value)
    return value


def _input():
    data = dict(frappe.form_dict)
    data.pop("cmd", None)
    if frappe.request.method == "POST":
        if not frappe.request.is_json:
            raise RfidError("error.invalid_request")
        body = frappe.request.get_json(silent=True)
        if not isinstance(body, dict):
            raise RfidError("error.invalid_request")
        data.update(body)
    return data


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def dispatch(operation=None):
    """Return one stable envelope inside Frappe's standard `message` wrapper."""
    try:
        operation = operation or frappe.request.args.get("operation") or frappe.form_dict.get("operation")
        handlers = READ if frappe.request.method == "GET" else WRITE if frappe.request.method == "POST" else {}
        if operation not in handlers:
            raise RfidError("error.method", 405)
        data = _input()
        result = handlers[operation](data)
        return {"success": True, "data": result, "message": message(SUCCESS[operation]) if operation in SUCCESS else ""}
    except RfidError as error:
        if frappe.request.method == "POST":
            frappe.db.rollback()
        frappe.local.response.http_status_code = error.status
        return {"success": False, "data": None, "errorCode": error.key, "message": str(error)}
    except (ValueError, TypeError):
        if frappe.request.method == "POST":
            frappe.db.rollback()
        frappe.local.response.http_status_code = 400
        return {"success": False, "data": None, "errorCode": "error.invalid_request",
                "message": message("error.invalid_request")}
    except Exception:
        if frappe.request.method == "POST":
            frappe.db.rollback()
        diagnostic = traceback.format_exc()
        frappe.log_error(
            title=message("diagnostic.api_operation", operation=operation),
            message=diagnostic,
        )
        frappe.local.response.http_status_code = 500
        return {"success": False, "data": None, "errorCode": "error.unexpected",
                "message": message("error.unexpected")}


def _photo_response(action):
    try:
        return action()
    except RfidError as error:
        if frappe.request.method == "POST":
            frappe.db.rollback()
        frappe.local.response.http_status_code = error.status
        return {"success": False, "data": None, "errorCode": error.key, "message": str(error)}
    except Exception:
        if frappe.request.method == "POST":
            frappe.db.rollback()
        frappe.log_error(title="RFID photo operation", message=traceback.format_exc())
        frappe.local.response.http_status_code = 500
        return {"success": False, "data": None, "errorCode": "error.unexpected",
                "message": message("error.unexpected")}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def upload_photo():
    def run():
        data = frappe.form_dict
        result = photos.upload(_device(data), data.get("sessionId"), data.get("requestId"),
                               frappe.request.files.get("file"))
        return {"success": True, "data": result, "message": ""}
    return _photo_response(run)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def photo_content(deviceId=None, sessionId=None, photoId=None, thumbnail=None):
    def run():
        from werkzeug.wrappers import Response

        content = photos.read(deviceId, sessionId, photoId, thumbnail == "1")
        return Response(content, mimetype="image/webp", headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'inline; filename="rfid-photo.webp"',
        })
    return _photo_response(run)
