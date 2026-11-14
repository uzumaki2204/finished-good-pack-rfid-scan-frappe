"""Tablet route backed by Frappe's standard Desk style."""

from pathlib import Path
import hashlib

import frappe

from finished_good_pack_rfid_scan import __version__
from finished_good_pack_rfid_scan.i18n import catalog, message


ROUTE = "finished-good-pack-rfid-scan"


def asset_version():
    root = Path(__file__).parent
    digest = hashlib.sha256()
    paths = sorted((root / "public" / "rfid").glob("*"))
    paths += sorted((root / "templates").rglob("*.html"))
    paths += [root / "i18n.json", root / "www" / "finished-good-pack-rfid-scan-sw.js"]
    for path in paths:
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return __version__ + "-" + digest.hexdigest()[:16]


def check_route():
    for doctype in ("Web Page", "Builder Page"):
        if frappe.db.exists("DocType", doctype):
            owner = frappe.db.get_value(doctype, {"route": ROUTE}, "name")
            if owner and (doctype != "Web Page" or owner != ROUTE):
                frappe.throw(message("error.route_conflict"), frappe.ValidationError)


def ensure_page():
    check_route()
    if frappe.db.exists("Web Page", ROUTE):
        return ROUTE
    html = Path(__file__).with_name("web_page.html").read_text(encoding="utf-8")
    frappe.get_doc({
        "doctype": "Web Page", "title": "Finished Good Pack RFID Scan", "route": ROUTE,
        "published": 1, "content_type": "HTML", "main_section_html": html,
        "full_width": 1, "show_title": 0, "show_sidebar": 0, "enable_comments": 0,
        "insert_style": 0, "css": "",
    }).insert(ignore_permissions=True, set_name=ROUTE)
    return ROUTE


def update_website_context(context):
    request = getattr(frappe.local, "request", None)
    if not request or request.path.rstrip("/") != "/" + ROUTE:
        return
    context.no_cache = 1
    context.show_sidebar = False
    context.no_breadcrumbs = True
    context.full_width = True
    context.base_template_path = "finished_good_pack_rfid_scan/templates/tablet_base.html"
    language = str(frappe.form_dict.get("lang") or "vi").split("-")[0]
    context.rfid_language = language if language in catalog() else "vi"
    context.rfid_catalog = catalog()
    context.rfid_asset_version = asset_version()
    head = frappe.get_template(
        "finished_good_pack_rfid_scan/templates/includes/tablet_head.html"
    ).render(context)
    context.head_include = (context.get("head_include") or "") + head
