"""Idempotent app-owned module, route and index setup."""

import frappe

from finished_good_pack_rfid_scan.i18n import message


REQUIRED_DOCTYPES = ("Company", "Market", "Factory Device")
ROLES = ("RFID Scan Manager", "RFID Scan Operator", "RFID Report Manager")


def _roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def _dependencies():
    for doctype in REQUIRED_DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            frappe.throw(message("error.missing_dependency", doctype=doctype), frappe.ValidationError)


def before_install():
    _dependencies()
    _roles()
    from finished_good_pack_rfid_scan.web_page import check_route

    check_route()


def before_migrate():
    _dependencies()
    _roles()


def after_migrate():
    from finished_good_pack_rfid_scan.web_page import ensure_page

    ensure_page()
    indexes = (
        ("RFID Scan Session", ["session_started_at", "name"], "fg_rfid_report_date"),
        ("RFID Scan Session", ["company", "status", "session_started_at"], "fg_rfid_session_scope"),
        ("RFID Booking Snapshot", ["session", "booking_id"], "fg_rfid_booking_scope"),
        ("RFID Scan Detail", ["company", "normalized_rfid"], "fg_rfid_duplicate_scope"),
        ("RFID Scan Detail", ["session", "scanned_at"], "fg_rfid_scan_session"),
    )
    for doctype, fields, index_name in indexes:
        if frappe.db.exists("DocType", doctype):
            frappe.db.add_index(doctype, fields, index_name)
    frappe.clear_cache()
