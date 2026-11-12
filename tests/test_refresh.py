import copy
import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_service import service
from finished_good_pack_rfid_scan import soap
from finished_good_pack_rfid_scan.plan import snapshot_version, booking_delta
from finished_good_pack_rfid_scan.errors import RfidError


def booking():
    return {"companyId": "C", "bookingId": "B", "headerPlannedCartonCount": 2,
            "headerActualCartonCount": 1, "plannedBoxCount": 2,
            "items": [{"finishedGoodPackDetailId": "I", "rfid": "R", "orderNo": "P", "dispPackNum": "1", "isMetalCheck": "N"}]}


class FingerprintTests(unittest.TestCase):
    def test_order_dates_and_translation_do_not_change_version(self):
        a = booking(); a["items"].append({"finishedGoodPackDetailId": "J"})
        b = copy.deepcopy(a); b["items"].reverse()
        b.update(downloadedAtUtc="later", expiresAtUtc="later", planningWarnings=["translated"])
        self.assertEqual(snapshot_version(a), snapshot_version(b))

    def test_content_edits_are_changes_without_new_ids(self):
        for field in ("rfid", "isMetalCheck", "colorName", "sizeName"):
            a = booking(); b = copy.deepcopy(a); b["items"][0][field] = "changed"
            self.assertTrue(booking_delta(a, b)["hasChanges"])
            self.assertEqual(booking_delta(a, b)["deltaStatus"], "Modified")


class SourceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.cache_data = {}
        self.cache = MagicMock()
        self.cache.get_value.side_effect = lambda k: copy.deepcopy(self.cache_data.get(k))
        self.cache.set_value.side_effect = lambda k,v,**kw: self.cache_data.update({k: copy.deepcopy(v)})
        self.header = {"innerBookingId": "B", "conPreShipPackCnt": 2, "conActShipPackCnt": 1}
        self.pack = {"innerPackNum": "K", "orderNo": "P", "doNo": "D", "dispPackNum": "1"}
        self.sources = [{"orderNo": "P", "doNo": "D", "usedPackNum": "1", "quantity": 1}]
        self.packs = {"K": self.pack}
        patches = [patch.object(soap.frappe, "cache", self.cache, create=True),
                   patch.object(soap, "_booking_sources", side_effect=lambda *a: ({}, "password", self.header, self.sources, self.packs)),
                   patch.object(soap, "_login", return_value="user"),
                   patch.object(soap, "_pack_details", return_value=[{"rfid": "R"}]),
                   patch.object(soap, "resolve_booking", return_value=booking()),
                   patch.object(soap.time, "time", return_value=1000)]
        self.mocks = [p.start() for p in patches]
        for p in patches: self.addCleanup(p.stop)
        self.read = self.mocks[3]

    def test_warm_light_check_has_no_detail_reads(self):
        _, first = soap.refresh_booking("C", "B")
        self.assertTrue(first["fullCheck"])
        self.read.reset_mock()
        _, second = soap.refresh_booking("C", "B")
        self.assertFalse(second["fullCheck"])
        self.read.assert_not_called()

    def test_booking_source_quantity_is_not_per_carton_rfid_count(self):
        self.sources[0]["quantity"] = 177
        self.pack["qtyPerSet"] = 1
        soap.refresh_booking("C", "B")
        self.read.reset_mock()
        soap.refresh_booking("C", "B")
        self.read.assert_not_called()

    def test_only_changed_pack_is_read(self):
        soap.refresh_booking("C", "B")
        self.read.reset_mock()
        self.packs["NEW"] = {**self.pack, "innerPackNum": "NEW", "dispPackNum": "2"}
        _, result = soap.refresh_booking("C", "B")
        self.assertEqual(result["detailCalls"], 1)
        self.assertEqual(self.read.call_args.args[2]["innerPackNum"], "NEW")

    def test_periodic_manual_and_final_checks_are_full(self):
        soap.refresh_booking("C", "B")
        with patch.object(soap.time, "time", return_value=1600):
            self.assertTrue(soap.refresh_booking("C", "B")[1]["fullCheck"])
        self.assertTrue(soap.refresh_booking("C", "B", full=True)[1]["fullCheck"])
        self.header["conActShipPackCnt"] = 2
        self.assertTrue(soap.refresh_booking("C", "B", previous=booking())[1]["fullCheck"])

    def test_partial_pack_is_retried_and_failed_read_keeps_cache(self):
        self.read.return_value = [{"rfid": ""}]
        soap.refresh_booking("C", "B")
        old = copy.deepcopy(self.cache_data)
        self.read.side_effect = RuntimeError("ERP offline")
        with self.assertRaises(RuntimeError): soap.refresh_booking("C", "B")
        self.assertEqual(old, self.cache_data)

    def test_cache_is_scoped_to_company(self):
        soap.refresh_booking("C", "B")
        self.assertTrue(soap.refresh_booking("OTHER", "B")[1]["fullCheck"])
        self.assertEqual(len(self.cache_data), 2)


class Row(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class OptimizedServiceTests(unittest.TestCase):
    def setUp(self):
        self.old = booking(); self.old["planVersion"] = snapshot_version(self.old)
        self.new = copy.deepcopy(self.old)
        self.device = types.SimpleNamespace(name="D", company="C")
        self.row = Row(name="S", company="C", device="D", status="Active")
        self.db = MagicMock()
        self.db.sql.side_effect = lambda sql,*a,**kw: [self.row] if "Scan Session" in sql else [types.SimpleNamespace(payload=json.dumps(self.old))]
        patches = [patch.object(service, "approved_device", return_value=self.device),
                   patch.object(service, "_session", return_value=self.row),
                   patch.object(service, "_load_bookings", side_effect=lambda *a: [copy.deepcopy(self.old)]),
                   patch.object(soap, "refresh_booking", side_effect=lambda *a,**kw: (copy.deepcopy(self.new), {"fullCheck": False, "checkedAtUtc": "now", "detailCalls": 0})),
                   patch.object(service.frappe, "db", self.db, create=True),
                   patch.object(service, "_save_snapshot"), patch.object(service, "_update_counts"),
                   patch.object(service.frappe, "get_doc", return_value=self.row, create=True)]
        self.mocks = [p.start() for p in patches]
        for p in patches: self.addCleanup(p.stop)

    def run_refresh(self, version=None):
        return service.refresh_optimized("D", "S", "B", client_version=version or self.old["planVersion"])

    def test_unchanged_is_small_without_snapshot_write(self):
        result = self.run_refresh()
        self.assertFalse(result["hasChanges"])
        self.assertNotIn("booking", result); self.assertNotIn("patch", result)
        self.mocks[5].assert_not_called(); self.mocks[6].assert_not_called()
        self.assertLess(len(json.dumps(result)), 400)

    def test_version_mismatch_returns_only_booking(self):
        result = self.run_refresh("offline-version")
        self.assertIn("booking", result); self.assertNotIn("session", result)

    def test_completed_while_loading_rejects_write(self):
        def read(*args, **kwargs):
            self.row.status = "Completed"
            return self.new, {}
        self.mocks[3].side_effect = read
        with self.assertRaises(RfidError): self.run_refresh()
        self.mocks[5].assert_not_called()

    def test_concurrent_snapshot_change_discards_response(self):
        def read(*args, **kwargs):
            self.old["items"][0]["rfid"] = "concurrent"
            return self.new, {}
        self.mocks[3].side_effect = read
        self.assertTrue(self.run_refresh()["stale"])
        self.mocks[5].assert_not_called()

    def test_changed_item_returns_patch_and_saves_once(self):
        self.new["items"][0]["isMetalCheck"] = "Y"
        result = self.run_refresh()
        self.assertTrue(result["hasChanges"])
        self.assertEqual(result["patch"]["upsert"][0]["isMetalCheck"], "Y")
        self.assertNotIn("items", result["patch"]["metadata"])
        self.assertNotIn("booking", result)
        self.mocks[5].assert_called_once(); self.mocks[6].assert_called_once()

    def test_device_changed_during_network_read_rejects(self):
        def read(*args, **kwargs):
            self.row.device = "OTHER"
            return self.new, {}
        self.mocks[3].side_effect = read
        with self.assertRaises(RfidError): self.run_refresh()
        self.mocks[5].assert_not_called()

    def test_network_read_happens_before_lock(self):
        def read(*args, **kwargs):
            self.db.sql.assert_not_called()
            return self.new, {}
        self.mocks[3].side_effect = read
        self.run_refresh()


if __name__ == "__main__":
    unittest.main()
