from urllib.parse import urlsplit

import frappe
from frappe.model.document import Document

from finished_good_pack_rfid_scan.i18n import message


class RFIDSOAPAccount(Document):
    def validate(self):
        url = urlsplit(self.service_url or "")
        if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password:
            frappe.throw(message("error.account_url"), frappe.ValidationError)
