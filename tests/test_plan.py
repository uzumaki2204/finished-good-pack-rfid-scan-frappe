import unittest
from datetime import datetime, timezone

from finished_good_pack_rfid_scan.errors import RfidError
from finished_good_pack_rfid_scan.plan import booking_delta, resolve_booking, validate_scans


def fixture():
    booking = {"innerBookingId": "B-1", "dispBookingId": "BOOK-1", "conPreShipPackCnt": 2, "conActShipPackCnt": 2}
    sources = [{"innerContainerId": "C-1", "orderNo": "PO-1", "doNo": "DO-1", "sampleCode": "US01", "usedPackNum": "BOX-1"},
               {"innerContainerId": "C-2", "orderNo": "PO-1", "doNo": "DO-1", "sampleCode": "US01", "usedPackNum": "BOX-2"}]
    packs = [{"innerPackNum": "P-1", "orderNo": "PO-1", "doNo": "DO-1", "sampleCode": "US01", "dispPackNum": "BOX-1", "itemCode": "SKU"}]
    details = {"P-1": [{"rfid": "RFID-1", "skuCode": "SKU", "colorCode": "BLK", "sizeCode": "M"}]}
    return resolve_booking("COMP-1", booking, sources, packs, details, lambda _: {"name": "US", "name_en": "USA"})


class PlanTest(unittest.TestCase):
    def test_maps_focused_carton_and_keeps_unmapped_warning(self):
        plan = fixture()
        self.assertEqual((plan["plannedBoxCount"], plan["mappedBoxCount"], plan["unmappedBoxCount"]), (2, 1, 1))
        self.assertEqual(plan["items"][0]["rfid"], "RFID-1")
        self.assertEqual(plan["items"][0]["marketId"], "US")
        self.assertTrue(plan["hasPlanningMismatch"])

    def test_rejects_booking_without_mapped_rfid(self):
        with self.assertRaises(RfidError) as error:
            resolve_booking("COMP-1", {"innerBookingId": "B-1"}, [], [], {}, lambda _: None)
        self.assertEqual(error.exception.key, "error.booking_unmapped")

    def test_server_snapshot_resolves_scan_and_rejects_duplicate(self):
        plan = fixture()
        item = plan["items"][0]
        scan = {"bookingId": plan["bookingId"], "finishedGoodPackDetailId": item["finishedGoodPackDetailId"],
                "rfid": "rfid-1", "scannedAtUtc": datetime.now(timezone.utc).isoformat(), "orderNo": "FORGED"}
        resolved = validate_scans([scan], [plan])
        self.assertEqual(resolved[0]["orderNo"], "PO-1")
        with self.assertRaises(RfidError) as error:
            validate_scans([scan, scan], [plan])
        self.assertEqual(error.exception.key, "error.scan_duplicate")

    def test_rejects_cross_booking_detail_substitution(self):
        plan = fixture()
        item = plan["items"][0]
        scan = {"bookingId": "OTHER", "finishedGoodPackDetailId": item["finishedGoodPackDetailId"],
                "rfid": item["rfid"], "scannedAtUtc": datetime.now(timezone.utc).isoformat()}
        with self.assertRaises(RfidError) as error:
            validate_scans([scan], [plan])
        self.assertEqual(error.exception.key, "error.scan_not_in_plan")

    def test_delta_reports_added_carton(self):
        old = fixture()
        new = {**old, "items": old["items"] + [{**old["items"][0], "finishedGoodPackDetailId": "SECOND", "dispPackNum": "BOX-2"}]}
        self.assertEqual(booking_delta(old, new)["deltaStatus"], "Expanded")


if __name__ == "__main__":
    unittest.main()
