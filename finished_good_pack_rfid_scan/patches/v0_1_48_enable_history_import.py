import frappe


def execute():
    for name in ("RFID Scan Session", "RFID Scan Detail"):
        for row in frappe.get_all("Property Setter", filters={"doc_type":name,"property":"allow_import"}, pluck="name"):
            frappe.delete_doc("Property Setter", row, ignore_permissions=True)
        for row in frappe.get_all("Custom DocPerm", filters={"parent":name,"role":["in",["System Manager","RFID Scan Manager"]]}, pluck="name"):
            frappe.db.set_value("Custom DocPerm", row, {"create":1,"write":1,"import":1})
        frappe.clear_cache(doctype=name)
