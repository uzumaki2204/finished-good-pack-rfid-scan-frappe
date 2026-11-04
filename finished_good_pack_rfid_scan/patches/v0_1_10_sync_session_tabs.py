"""Refresh the saved tablet page with the session tabs and completion form."""

from pathlib import Path

import frappe

from finished_good_pack_rfid_scan.web_page import ROUTE, check_route


def execute():
    check_route()
    if not frappe.db.exists("Web Page", ROUTE):
        from finished_good_pack_rfid_scan.web_page import ensure_page

        ensure_page()
        return

    page = frappe.get_doc("Web Page", ROUTE)
    page.main_section_html = Path(__file__).parents[1].joinpath("web_page.html").read_text(encoding="utf-8")
    page.title = "Finished Good Pack RFID Scan"
    page.published = 1
    page.full_width = 1
    page.show_title = 0
    page.show_sidebar = 0
    page.enable_comments = 0
    page.insert_style = 0
    page.css = ""
    page.save(ignore_permissions=True)
