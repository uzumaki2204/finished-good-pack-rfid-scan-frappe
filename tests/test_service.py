import sys
import types
import unittest
from unittest.mock import patch


try:
    import frappe  # noqa: F401
except ImportError:
    sys.modules["frappe"] = types.ModuleType("frappe")

from finished_good_pack_rfid_scan import service
from finished_good_pack_rfid_scan.errors import RfidError
from test_plan import fixture


class ServicePolicyTest(unittest.TestCase):
    def setUp(self):
        self.device = types.SimpleNamespace(name="DEVICE-1", company="COMP-1")

    def test_company_view_never_grants_session_mutations(self):
        record = types.SimpleNamespace(name="SESSION-1", company="COMP-1", device="OWNER", status="Active")
        fake_db = types.SimpleNamespace(exists=lambda *_: True, sql=lambda *_: None)
        with patch.object(service, "approved_device", return_value=self.device), \
             patch.object(service.frappe, "db", fake_db, create=True), \
             patch.object(service.frappe, "get_doc", return_value=record, create=True), \
             patch.object(service, "_details", return_value={"sessionId": record.name}):
            for status in ("Active", "Completed"):
                record.status = status
                self.assertTrue(service.get_session(self.device.name, record.name)["readOnly"])
                actions = [lambda: service.complete(self.device.name, record.name, "", "", "", []),
                    lambda: service.sync_scans(self.device.name, record.name, [{}]),
                    lambda: service.delete_session(self.device.name, record.name),
                    lambda: service.refresh_delta(self.device.name, record.name, "B"),
                    lambda: service.rehydrate(self.device.name, record.name)]
                for action in actions:
                    with self.assertRaises(RfidError) as error: action()
                    self.assertEqual(error.exception.status,403)
            record.status = "Deleted"
            with self.assertRaises(RfidError): service.get_session(self.device.name, record.name)
            record.status = "Active"; record.company = "OTHER"
            with self.assertRaises(RfidError): service.get_session(self.device.name, record.name)

    def test_start_requires_conflict_confirmation_after_company_lock(self):
        booking = fixture()
        fake_db = types.SimpleNamespace(sql=lambda *_: None)
        with patch.object(service, "approved_device", return_value=self.device), \
             patch.object(service, "preload_booking", return_value=booking), \
             patch.object(service, "preview_conflicts", return_value={"sessions": [{"sessionId": "OTHER"}]}), \
             patch.object(service.frappe, "db", fake_db, create=True):
            with self.assertRaises(RfidError) as error:
                service.start_session(self.device.name, ["B-1"])
        self.assertEqual((error.exception.key, error.exception.status), ("error.session_conflict", 409))

    def test_session_rejects_other_company(self):
        record = types.SimpleNamespace(name="SESSION-1", company="OTHER-COMPANY", device="DEVICE-1", status="Active")
        fake_db = types.SimpleNamespace(exists=lambda *_: True)
        with patch.object(service.frappe, "db", fake_db, create=True), \
             patch.object(service.frappe, "get_doc", return_value=record, create=True):
            with self.assertRaises(RfidError) as error:
                service._session(record.name, self.device)
        self.assertEqual(error.exception.status, 404)

    def test_completion_rejects_scan_outside_server_snapshot(self):
        record = types.SimpleNamespace(name="SESSION-1", company="COMP-1", device="DEVICE-1", status="Active")
        with patch.object(service, "approved_device", return_value=self.device), \
             patch.object(service, "_session", return_value=record), \
             patch.object(service, "_load_bookings", return_value=[fixture()]), \
             patch.object(service, "_load_scans", return_value=[]):
            with self.assertRaises(RfidError) as error:
                service.complete(self.device.name, record.name, "51A-12345", "Driver", "", [
                    {"bookingId": "B-1", "finishedGoodPackDetailId": "FORGED", "rfid": "RFID-1", "scannedAtUtc": "2026-01-01T00:00:00Z"}
                ])
        self.assertEqual(error.exception.key, "error.scan_not_in_plan")


if __name__ == "__main__":
    unittest.main()
