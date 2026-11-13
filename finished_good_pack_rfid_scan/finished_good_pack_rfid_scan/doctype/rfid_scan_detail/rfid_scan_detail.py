import frappe
from frappe.model.document import Document
from finished_good_pack_rfid_scan import scan_storage
from finished_good_pack_rfid_scan.plan import rfid_key


class RFIDScanDetail(Document):
    def validate(self):
        previous = self.get_doc_before_save()
        if not previous:
            return
        try:
            source = scan_storage.edited_scan_fields(previous.as_dict(), self.as_dict())
            if self.has_value_changed("is_metal_check"):
                source["isMetalCheck"] = "Y" if self.is_metal_check else "N"
            elif self.has_value_changed("source_metal_check"):
                from finished_good_pack_rfid_scan.service import _metal
                self.is_metal_check = int(_metal(source.get("isMetalCheck")))
            if self.has_value_changed("scanned_at"):
                from frappe.utils import get_datetime
                source["scannedAtUtc"] = get_datetime(self.scanned_at).isoformat() + "+00:00"
            elif self.has_value_changed("source_scanned_at"):
                from datetime import datetime, timezone
                occurred = datetime.fromisoformat(str(self.source_scanned_at).replace("Z", "+00:00"))
                if occurred.tzinfo:
                    occurred = occurred.astimezone(timezone.utc).replace(tzinfo=None)
                self.scanned_at = occurred
            self.update(scan_storage.encode_scan(source, self.as_dict()))
            self.normalized_rfid = rfid_key(self.rfid)
            from finished_good_pack_rfid_scan.service import _hash
            self.scan_key = _hash(self.session, self.booking_id, self.detail_id)
            if frappe.db.exists("RFID Scan Detail", {"session":self.session,"normalized_rfid":self.normalized_rfid,"name":["!=",self.name]}):
                raise ValueError("RFID đã tồn tại trong phiên")
        except (ValueError, TypeError, OverflowError) as error:
            frappe.throw("Không thể lưu dữ liệu RFID: " + str(error), frappe.ValidationError)
        owner = frappe.db.get_value("RFID Scan Session", self.session, ["company", "device"], as_dict=True)
        if not owner or owner.company != self.company or owner.device != self.device:
            frappe.throw("Công ty và thiết bị phải khớp với phiên quét.", frappe.ValidationError)

    def on_update(self):
        previous = self.get_doc_before_save()
        if not previous:
            return
        for session in {previous.session, self.session}:
            if frappe.db.get_value("RFID Scan Session", session, "status") == "Completed":
                counts = frappe.db.sql("SELECT COUNT(*), COALESCE(SUM(is_metal_check),0) FROM `tabRFID Scan Detail` WHERE session=%s", (session,))[0]
                frappe.db.set_value("RFID Scan Session", session, {"total_scanned_count": counts[0], "metal_checked_count": counts[1]}, update_modified=False)
