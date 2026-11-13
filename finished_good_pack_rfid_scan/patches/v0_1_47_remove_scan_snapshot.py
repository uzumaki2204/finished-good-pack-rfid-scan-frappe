"""Remove retired scan JSON storage; Booking plan snapshots are unchanged."""
import frappe


def execute():
    table = "RFID Scan Detail"
    if frappe.db.has_column(table, "payload"):
        # Existing converted Dev rows remain readable. Never discard an unconverted row.
        pending = frappe.db.sql("SELECT COUNT(*) FROM `tabRFID Scan Detail` WHERE COALESCE(storage_version,0)!=1")[0][0]
        if pending:
            frappe.throw("Còn dữ liệu RFID chưa chuyển sang trường riêng. Hãy chuyển dữ liệu trước khi xóa Scan Snapshot.")
        frappe.db.sql("ALTER TABLE `tabRFID Scan Detail` DROP COLUMN `payload`")
    if frappe.db.has_column(table, "storage_error"):
        frappe.db.sql("ALTER TABLE `tabRFID Scan Detail` DROP COLUMN `storage_error`")
    for row in frappe.get_all("Property Setter", filters={"doc_type":table,"field_name":["in",["payload","storage_error"]]}, pluck="name"):
        frappe.delete_doc("Property Setter", row, ignore_permissions=True)
    frappe.clear_cache(doctype=table)
    for name in ("RFID Scan Detail", "RFID Scan Session", "RFID Booking Snapshot", "RFID Session Photo", "RFID SOAP Account"):
        meta = frappe.get_meta(name)
        editable = [field.fieldname for field in meta.fields if not field.hidden]
        for row in frappe.get_all("Property Setter", filters={"doc_type":name,"field_name":["in",editable],"property":"read_only"}, pluck="name"):
            frappe.delete_doc("Property Setter", row, ignore_permissions=True)
        for row in frappe.get_all("Custom DocPerm", filters={"parent":name,"role":["in",["System Manager","RFID Scan Manager"]]}, fields=["name","role"]):
            if row.role == "System Manager" or name != "RFID Session Photo":
                frappe.db.set_value("Custom DocPerm", row.name, "write", 1)
        frappe.clear_cache(doctype=name)
