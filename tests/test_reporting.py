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
from finished_good_pack_rfid_scan.report_print import render


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
        for method, args in [(report.print_report, ()), (report.options, ()), (report.overview, ()), (report.detail, ("S",)),
                             (report.photo_list, ("S",)), (report.photo_content, ("S", "P"))]:
            with self.assertRaises(PermissionError): method(*args)
        self.db.sql.assert_not_called()

    def test_options_only_include_existing_session_data_without_date_filter(self):
        self.db.sql.side_effect = [
            [types.SimpleNamespace(company="C1", device="D1", status="Completed")],
            [types.SimpleNamespace(booking_id="B1", orders='["PO1", "PO1"]')],
        ]
        result = report.options()
        self.assertEqual(result["bookings"], ["B1"])
        self.assertEqual(result["orders"], ["PO1"])
        self.assertEqual(result["statuses"], ["Completed"])
        calls = frappe.get_all.call_args_list
        self.assertEqual(calls[0].kwargs["filters"], {"name": ["in", ["C1"]]})
        self.assertEqual(calls[1].kwargs["filters"], {"name": ["in", ["D1"]]})
        for call in self.db.sql.call_args_list:
            self.assertIn("IN ('Active', 'Completed')", call.args[0])
            self.assertNotIn("session_started_at", call.args[0])

    def test_empty_options_do_not_list_all_master_records(self):
        self.db.sql.return_value = []
        self.assertEqual(report.options(), dict(companies=[], devices=[], statuses=[], bookings=[], orders=[]))
        frappe.get_all.assert_not_called()

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
            payload=json.dumps({"usedPackNum":"OLD","setCode":"I055","sampleCode":"07217H060C","colorName":"BLUE"}))]
        with patch.object(report,"summaries",return_value=[{"sessionId":"S1"}]):
            result=report.detail("S1",page=139)
        self.assertEqual(frappe.get_all.call_args.kwargs["limit_start"],13800)
        self.assertEqual(frappe.get_all.call_args.kwargs["limit_page_length"],100)
        self.assertEqual(result["items"][0]["boxCode"],"I055")
        self.assertEqual(result["items"][0]["item"],"217H060C")
        self.assertIsNone(result["items"][0]["marketCode"])
        self.assertEqual(result["total"],13868)

    def test_detail_filters_use_bound_values_and_payload_codes(self):
        where, args = report.detail_where("S1", dict(box="00001", item="217H060C", market="07", color="X' OR 1=1", size="L", metal="Y", booking="B1", po="PO1"))
        self.assertNotIn(args["color"], where)
        self.assertIn("$.sampleCode", where)
        self.assertIn("SUBSTRING", where)
        self.assertIn("$.sizeName", where)
        self.assertEqual(len(args), 9)
        self.assertIn("booking_id=%(booking)s", where)
        self.assertIn("order_no=%(po)s", where)
        with self.assertRaises(ValueError): report.detail_where("S1", {"metal":"invalid"})

    def test_filtered_count_and_pagination_use_same_conditions(self):
        frappe.get_doc.return_value = record()
        self.db.sql.side_effect = [[[201]], [], []]
        with patch.object(report, "summaries", return_value=[{}]):
            result = report.detail("S1", page=2, box="00001", item="217H060C", metal="N")
        self.assertEqual(result["total"], 201)
        calls = self.db.sql.call_args_list
        for key in ("session", "box", "item", "metal"):
            self.assertEqual(calls[0].args[1][key], calls[2].args[1][key])
        self.assertEqual(calls[2].args[1]["offset"], 100)
        self.assertEqual(calls[2].args[1]["limit"], 100)

    def test_po_fallback_uses_saved_details_and_legacy_summaries(self):
        expression = report.stored_orders_sql("b.payload")
        self.assertIn("$.summaryRows[*].orderNo", expression)
        self.assertIn("$.items[*].orderNo", expression)
        where, args = report.where_clause({"po": "PO-OLD"})
        self.assertIn("d.order_no=%(po)s", where)
        self.assertNotIn("PO-OLD", where)
        self.assertEqual(report.stored_orders('["P1", "P1", null, ""]'), {"P1"})

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

    def test_print_html_escapes_data_and_matches_excel_columns(self):
        html = render([{"po":"<script>alert(1)</script>","rfid":"RFID-LAST","box":"00001"}],
                      session={"bookingIds":["B1"],"status":"Active","driver":"<img src=x>","plannedItems":0,"plannedBoxes":0})
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",html)
        self.assertIn("&lt;img src=x&gt;",html)
        self.assertIn("BÁO CÁO CHI TIẾT SCAN RFID LOAD CONT",html)
        self.assertIn("Chưa đồng bộ dữ liệu scan",html)
        self.assertIn("00001",html)
        self.assertEqual(html.count('scope="col"'),14)
        self.assertIn("RFID-LAST",html)
        html = render([],filters={"from_date":"01/11/2026","company":"C"})
        self.assertIn("BÁO CÁO TỔNG QUAN SCAN RFID LOAD CONT",html)
        self.assertIn("Không có dữ liệu",html)
        self.assertEqual(html.count('scope="col"'),14)

    def test_print_has_extra_booking_column_only_for_multi_booking(self):
        html=render([],session={"bookingIds":["B1","B2"]})
        self.assertEqual(html.count('scope="col"'),15)

    def test_print_all_detail_batches_and_deny_deleted(self):
        response_module=types.ModuleType("werkzeug.wrappers")
        response_module.Response=lambda content,**kwargs: {"content":content,**kwargs}
        frappe.get_doc.return_value=record()
        with patch.dict(sys.modules,{"werkzeug.wrappers":response_module}), \
             patch.object(report,"summaries",return_value=[{"bookingIds":["B1"],"status":"Completed"}]), \
             patch.object(report,"scan_items",side_effect=[[{"rfid":str(i)} for i in range(500)],[{"rfid":"LAST-501"}]]) as scans:
            result=report.print_report(session_id="S1")
            self.assertIn("LAST-501",result["content"])
            self.assertIn("501 dòng",result["content"])
            self.assertEqual(scans.call_args.args[:3],("S1",500,500))
            self.assertEqual(result["headers"]["Cache-Control"],"private, no-store")
            frappe.get_doc.return_value=record(status="Deleted")
            with self.assertRaises(LookupError):report.print_report(session_id="S1")

    def test_print_overview_not_limited_to_first_page(self):
        response_module=types.ModuleType("werkzeug.wrappers")
        response_module.Response=lambda content,**kwargs: content
        self.db.sql.return_value=[record(name=f"S{i}") for i in range(55)]
        def summaries(rows):return [{"company":r.name} for r in rows]
        with patch.dict(sys.modules,{"werkzeug.wrappers":response_module}), patch.object(report,"summaries",side_effect=summaries):
            html=report.print_report(from_date="2026-11-01",to_date="2026-11-12",booking="B1")
        self.assertIn("55 dòng",html)
        self.assertIn("S54",html)
        self.assertNotIn("LIMIT",self.db.sql.call_args.args[0])
        self.assertEqual(self.db.sql.call_args.args[1]["booking"],"B1")


if __name__ == "__main__":
    unittest.main()
