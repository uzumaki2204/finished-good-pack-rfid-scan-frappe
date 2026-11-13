import json
import frappe
from frappe.model.document import Document


class RFIDScanSession(Document):
    def validate(self):
        if not frappe.flags.in_import:
            return
        if self.status != "Completed":
            frappe.throw("Import lịch sử chỉ nhận phiên Completed.", frappe.ValidationError)
        if not self.session_completed_at:
            frappe.throw("Cần nhập thời gian hoàn thành phiên lịch sử.", frappe.ValidationError)
        if frappe.db.get_value("Factory Device", self.device, "company") != self.company:
            frappe.throw("Thiết bị không thuộc công ty đã chọn.", frappe.ValidationError)
        try:
            bookings = json.loads(self.booking_ids_json)
            if not isinstance(bookings, list) or not bookings or any(not isinstance(x,str) or not x.strip() for x in bookings):
                raise ValueError
        except (ValueError, TypeError):
            frappe.throw('Booking IDs phải là danh sách JSON, ví dụ ["B26110300003"].', frappe.ValidationError)
