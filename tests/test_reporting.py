import json
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

try:
    import frappe
except ImportError:
    frappe = types.ModuleType("frappe")
    sys.modules["frappe"] = frappe
if not hasattr(frappe, "whitelist"):
    frappe.whitelist = lambda **kwargs: lambda fn: fn

from finished_good_pack_rfid_scan import reporting as report


def record(**changes):
    return types.SimpleNamespace(**{**dict(name="S1", company="C1", device="D1", status="Completed",
        booking_ids_json='["B1", "B2"]', vehicle_plate_number="V", driver_full_name="Driver", note="",
        session_started_at=datetime(2026, 11, 1), session_completed_at=datetime(2026, 11, 2),
        planned_item_count=10, planned_box_count=3, total_scanned_count=8, metal_checked_count=7), **changes})


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        def throwing(message, exception):
            raise exception(message)
        for name, value in dict(db=self.db, session=types.SimpleNamespace(user="Manager"),
            get_roles=lambda: ["RFID Report Manager"], throw=throwing,
            PermissionError=PermissionError, ValidationError=ValueError, DoesNotExistError=LookupError,
            get_all=MagicMock(), get_doc=MagicMock()).items():
            patcher = patch.object(frappe, name, value, create=True)
            patcher.start(); self.addCleanup(patcher.stop)

    def test_roles_and_guest(self):
        for user, roles, allowed in [("Guest", ["System Manager"], False), ("Operator", ["RFID Scan Operator"], False),
                                     ("M", ["RFID Report Manager"], True), ("A", ["System Manager"], True)]:
            frappe.session.user = user
            with patch.object(frappe, "get_roles", return_value=roles):
                self.assertEqual(report.can_open(), allowed)
                if allowed: report.authorize()
                else:
                    with self.assertRaises(PermissionError): report.authorize()

    def test_every_endpoint_checks_authority(self):
        frappe.session.user = "Guest"
        for method, args in [(report.options, ()), (report.overview, ()), (report.detail, ("S",)),
                             (report.photo_list, ("S",)), (report.photo_content, ("S", "P"))]:
            with self.assertRaises(PermissionError): method(*args)
        self.db.sql.assert_not_called()

    def test_date_bounds_vietnam_and_invalid(self):
        self.assertEqual(report.date_bounds("2026-11-01", "2026-11-12"),
                         (datetime(2026, 10, 31, 17), datetime(2026, 11, 12, 17)))
        for start,end in [("invalid", "2026-11-12"), ("2026-11-13", "2026-11-12")]:
            with self.assertRaises(ValueError): report.date_bounds(start,end)

    def test_filters_parameterized_and_deleted_excluded(self):
        where,args = report.where_clause(dict(company="C' OR 1=1 --", booking="B", po="PO", status="Active"))
        self.assertNotIn(args["company"], where)
        self.assertIn("s.status IN ('Active', 'Completed')", where)
        self.assertIn("JSON_CONTAINS", where)
        with self.assertRaises(ValueError): report.where_clause({"status":"Deleted"})

    def test_large_result_page_is_bounded(self):
        self.db.sql.side_effect = [[[13868]], []]
        result = report.overview(page="278")
        self.assertEqual((result["total"],result["page"],result["pageSize"]), (13868,278,50))
        args = self.db.sql.call_args.args[1]
        self.assertEqual((args["offset"],args["limit"]), (13850,50))
        for page in (0,-1,"1.1","bad"):
            with self.assertRaises(ValueError): report.page_number(page)

    def test_deleted_session_blocked_for_details_and_photos(self):
        frappe.get_doc.return_value = record(status="Deleted")
        for method,args in [(report.detail,("S",)), (report.photo_list,("S",)), (report.photo_content,("S","P"))]:
            with self.assertRaises(LookupError): method(*args)

    def test_summary_separates_sessions_and_hides_active_scan_metrics(self):
        self.db.sql.side_effect = [[types.SimpleNamespace(session="S1",orders='["PO1"]'),
                                   types.SimpleNamespace(session="S2",orders='["PO1", "PO2"]')],
                                  [types.SimpleNamespace(session="S1",n=2)]]
        frappe.get_all.side_effect = [[types.SimpleNamespace(name="C1",company_name="Company")],
                                     [types.SimpleNamespace(name="D1",device_name="Device")]]
        rows = report.summaries([record(),record(name="S2",status="Active")])
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["bookingIds"],["B1","B2"])
        self.assertEqual(rows[0]["scannedBoxes"],2)
        self.assertEqual(rows[1]["plannedItems"],10)
        for key in ("scannedItems","metalChecked","scannedBoxes"): self.assertIsNone(rows[1][key])
        self.assertIn("GROUP BY session, booking_id, order_no, do_no, disp_pack_num",self.db.sql.call_args.args[0])

    def test_detail_uses_frozen_payload_missing_fields_and_100_row_page(self):
        frappe.get_doc.return_value = record()
        self.db.count.return_value = 13868
        frappe.get_all.return_value = [types.SimpleNamespace(booking_id="B",order_no="PO",do_no="DO",item_code="I",
            disp_pack_num="00001",rfid="R",is_metal_check=1,scanned_at=datetime(2026,11,1),
            payload=json.dumps({"usedPackNum":"I055","colorName":"BLUE"}))]
        with patch.object(report,"summaries",return_value=[{"sessionId":"S1"}]):
            result=report.detail("S1",page=139)
        self.assertEqual(frappe.get_all.call_args.kwargs["limit_start"],13800)
        self.assertEqual(frappe.get_all.call_args.kwargs["limit_page_length"],100)
        self.assertEqual(result["items"][0]["boxCode"],"I055")
        self.assertIsNone(result["items"][0]["marketCode"])
        self.assertEqual(result["total"],13868)

    def test_photo_cursor_and_no_public_paths(self):
        frappe.get_doc.return_value=record()
        frappe.get_all.return_value=[types.SimpleNamespace(name=f"P{i}",original_name="a",width=1,height=1,byte_size=1,creation="now") for i in range(25)]
        result=report.photo_list("S1",before="P100")
        self.assertEqual(len(result["items"]),24)
        self.assertEqual(result["nextCursor"],"P23")
        self.assertEqual(frappe.get_all.call_args.kwargs["filters"]["name"],["<","P100"])
        self.assertNotIn("file_url",str(result))

    def test_photo_wrong_session_deleted_or_wrong_attachment(self):
        for photo in [types.SimpleNamespace(session="Other",deleted=0),types.SimpleNamespace(session="S1",deleted=1)]:
            frappe.get_doc.side_effect=[record(),photo]
            with self.assertRaises(LookupError): report.photo_content("S1","P")
        photo=types.SimpleNamespace(session="S1",deleted=0,name="P",image_file="F")
        for file in [types.SimpleNamespace(is_private=0),types.SimpleNamespace(is_private=1,attached_to_doctype="Other")]:
            frappe.get_doc.side_effect=[record(),photo,file]
            with self.assertRaises(LookupError): report.photo_content("S1","P")


if __name__ == "__main__":
    unittest.main()
