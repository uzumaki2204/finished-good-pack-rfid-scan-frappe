"""Install the read-only management page without assigning users new roles."""
import frappe
from finished_good_pack_rfid_scan.install import _roles


def execute():
    _roles()
    frappe.reload_doc("finished_good_pack_rfid_scan", "page", "rfid_load_cont_report")
    frappe.clear_cache()
