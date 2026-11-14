import sys
import types
import unittest
from datetime import datetime, timezone
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

    def test_background_sync_only_checks_new_batch_and_is_idempotent(self):
        plan = fixture()
        item = plan["items"][0]
        scan = {"bookingId": plan["bookingId"], "finishedGoodPackDetailId": item["finishedGoodPackDetailId"],
                "rfid": item["rfid"], "scannedAtUtc": datetime.now(timezone.utc).isoformat()}
        saved = []
        session = types.SimpleNamespace(name="SESSION-1", status="Active", total_scanned_count=0,
                                        metal_checked_count=0, save=lambda **_: saved.append(True))
        name = service._hash(session.name, scan["bookingId"], scan["finishedGoodPackDetailId"])
        rows = []
        db = types.SimpleNamespace(sql=lambda *_: None, get_all=lambda *_args, **kwargs:
                                   rows if "name" in kwargs["filters"] else [])
        with patch.object(service.frappe, "db", db, create=True), \
             patch.object(service, "_insert_scans") as insert, \
             patch.object(service, "_load_scans", side_effect=AssertionError("Full scan read")):
            first = service._sync_batch(self.device, session, [scan], [plan])
            self.assertEqual(first["syncedCount"], 1)
            self.assertEqual(insert.call_count, 1)
            rows.append(types.SimpleNamespace(name=name, rfid=scan["rfid"]))
            second = service._sync_batch(self.device, session, [scan], [plan])
            self.assertEqual(second["syncedCount"], 1)
            self.assertEqual(insert.call_count, 1)
            self.assertEqual(len(saved), 1)

    def test_background_sync_rejects_existing_rfid_for_another_detail(self):
        plan = fixture()
        item = plan["items"][0]
        scan = {"bookingId": plan["bookingId"], "finishedGoodPackDetailId": item["finishedGoodPackDetailId"],
                "rfid": item["rfid"], "scannedAtUtc": datetime.now(timezone.utc).isoformat()}
        session = types.SimpleNamespace(name="SESSION-1", status="Active", total_scanned_count=0,
                                        metal_checked_count=0)
        db = types.SimpleNamespace(sql=lambda *_: None, get_all=lambda *_args, **kwargs: [] if "name" in kwargs["filters"] else
                                   [types.SimpleNamespace(name="OTHER", normalized_rfid=service.rfid_key(scan["rfid"]))])
        with patch.object(service.frappe, "db", db, create=True), \
             patch.object(service, "_insert_scans") as insert:
            with self.assertRaises(RfidError) as error:
                service._sync_batch(self.device, session, [scan], [plan])
            self.assertEqual(error.exception.key, "error.scan_duplicate")
            insert.assert_not_called()

    def test_compact_completion_uses_stored_scans_without_full_response(self):
        plan = fixture()
        item = plan["items"][0]
        scan = {"bookingId": plan["bookingId"], "finishedGoodPackDetailId": item["finishedGoodPackDetailId"],
                "rfid": item["rfid"], "scannedAtUtc": datetime.now(timezone.utc).isoformat()}
        stored = service.validate_scans([scan], [plan])
        session = types.SimpleNamespace(name="SESSION-1", status="Active", company=self.device.company,
            vehicle_plate_number="", driver_full_name="", note="", session_completed_at=None,
            total_scanned_count=1, metal_checked_count=0, cross_session_duplicate_count=0,
            save=lambda **_: None)
        with patch.object(service, "approved_device", return_value=self.device), \
             patch.object(service, "_session", return_value=session), \
             patch.object(service, "_load_bookings", return_value=[plan]), \
             patch.object(service, "_load_scans", return_value=stored), \
             patch.object(service, "_duplicate_rfids", return_value=0), \
             patch.object(service, "_insert_scans") as insert, \
             patch.object(service, "_details", side_effect=AssertionError("Full response")), \
             patch.object(service.frappe, "db", types.SimpleNamespace(sql=lambda *_: None), create=True):
            result = service.complete(self.device.name, session.name, "51A-12345", "Driver", "", [], compact=True)
            self.assertEqual(result["sessionStatus"], "Completed")
            self.assertEqual(result["totalScannedCount"], 1)
            insert.assert_called_once_with(self.device, session.name, [])

    def test_duplicate_check_batches_large_session(self):
        scans = [{"rfid": f"TAG-{index}"} for index in range(4500)]
        queries = []
        def get_all(_doctype, **kwargs):
            queries.append(kwargs["filters"]["normalized_rfid"][1])
            return [types.SimpleNamespace(normalized_rfid="TAG-12")] if "TAG-12" in queries[-1] else []
        with patch.object(service.frappe, "db", types.SimpleNamespace(get_all=get_all), create=True):
            self.assertEqual(service._duplicate_rfids(self.device, "SESSION-1", scans), 1)
        self.assertEqual(len(queries), 9)
        self.assertTrue(all(len(chunk) <= 500 for chunk in queries))


if __name__ == "__main__":
    unittest.main()
