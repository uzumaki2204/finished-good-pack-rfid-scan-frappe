import frappe
from frappe.model.document import Document
from finished_good_pack_rfid_scan import scan_storage
from finished_good_pack_rfid_scan.plan import rfid_key


class RFIDScanDetail(Document):
    def before_insert(self):
        if self.storage_version == 1 and self.source_layout and not frappe.flags.in_import:
            return
        from finished_good_pack_rfid_scan.service import _hash
        from frappe.utils import get_datetime
        self.flags.rfid_manual_insert = True
        self.normalized_rfid = rfid_key(self.rfid)
        self.scan_key = _hash(self.session, self.booking_id, self.detail_id)
        source = {key: self.get(field) for key, field in scan_storage.FIELDS.items()
                  if self.get(field) not in (None, "")}
        source.setdefault("scannedAtUtc", get_datetime(self.scanned_at).isoformat() + "+00:00")
        source.setdefault("isMetalCheck", "Y" if self.is_metal_check else "N")
        try:
            self.update(scan_storage.encode_scan(source, self.as_dict()))
        except (ValueError, TypeError, OverflowError) as error:
            frappe.throw("Không thể nhập RFID: " + str(error), frappe.ValidationError)

    def validate(self):
        previous = self.get_doc_before_save()
        if not previous:
            if self.flags.rfid_manual_insert:
                self.validate_owner()
                if not self.rfid or not self.normalized_rfid or not self.booking_id or not self.detail_id or not self.scanned_at:
                    frappe.throw("Cần nhập RFID, Booking, Pack Detail ID và thời gian scan.", frappe.ValidationError)
                if frappe.db.exists("RFID Scan Detail", {"session":self.session,"normalized_rfid":self.normalized_rfid}):
                    frappe.throw("RFID đã tồn tại trong phiên.", frappe.ValidationError)
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
        self.validate_owner()

    def validate_owner(self):
        owner = frappe.db.get_value("RFID Scan Session", self.session, ["company", "device", "status", "booking_ids_json"], as_dict=True)
        if not owner or owner.company != self.company or owner.device != self.device:
            frappe.throw("Công ty và thiết bị phải khớp với phiên quét.", frappe.ValidationError)

        if frappe.flags.in_import:
            import json
            if owner.status != "Completed" or self.booking_id not in json.loads(owner.booking_ids_json or "[]"):
                frappe.throw("Chi tiết import phải thuộc Booking của phiên Completed.", frappe.ValidationError)

    def on_update(self):
        previous = self.get_doc_before_save()
        if not previous and not self.flags.rfid_manual_insert:
            return
        for session in ({previous.session, self.session} if previous else {self.session}):
            if frappe.db.get_value("RFID Scan Session", session, "status") == "Completed":
                counts = frappe.db.sql("SELECT COUNT(*), COALESCE(SUM(is_metal_check),0) FROM `tabRFID Scan Detail` WHERE session=%s", (session,))[0]
                frappe.db.set_value("RFID Scan Session", session, {"total_scanned_count": counts[0], "metal_checked_count": counts[1]}, update_modified=False)
