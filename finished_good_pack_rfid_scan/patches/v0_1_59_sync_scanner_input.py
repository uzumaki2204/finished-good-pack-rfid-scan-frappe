"""Update the stored scan page for Android hardware scanner input."""

from pathlib import Path

import frappe

from finished_good_pack_rfid_scan.web_page import ROUTE, check_route, ensure_page


def execute():
    check_route()
    if not frappe.db.exists("Web Page", ROUTE):
        ensure_page()
        return

    page = frappe.get_doc("Web Page", ROUTE)
    page.main_section_html = Path(__file__).parents[1].joinpath("web_page.html").read_text(encoding="utf-8")
    page.save(ignore_permissions=True)
