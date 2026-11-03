"""Shared Factory Device approval and RFID Desk access."""

import frappe

from finished_good_pack_rfid_scan.errors import RfidError


def can_open():
    """The Desk shortcut is visible to signed-in users; tablet operations check Factory Device separately."""
    return frappe.session.user != "Guest"


def approved_device(device_id):
    if not isinstance(device_id, str) or not device_id.strip():
        raise RfidError("error.device_missing", 403)
    device = frappe.db.get_value(
        "Factory Device", device_id.strip(),
        ["name", "device_name", "status", "is_active", "company"], as_dict=True,
    )
    if not device:
        raise RfidError("error.device_missing", 403)
    if device.status != "Approved" or not device.is_active or not device.company:
        raise RfidError("error.device_pending", 403)
    return device


def device_data(device):
    return {
        "id": device.name,
        "deviceName": device.device_name or device.name,
        "companyId": device.company,
        "companyName": frappe.db.get_value("Company", device.company, "company_name") or device.company,
        "status": device.status,
        "isActive": bool(device.is_active),
    }
