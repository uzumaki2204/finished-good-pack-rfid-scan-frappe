import sys
import types
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET


try:
    import frappe  # noqa: F401
except ImportError:
    sys.modules["frappe"] = types.ModuleType("frappe")

from finished_good_pack_rfid_scan import soap


def xml(body):
    return ET.fromstring(body)


class SoapContractTest(unittest.TestCase):
    def setUp(self):
        self.account = types.SimpleNamespace(service_url="https://example.invalid/soap", username="sample", login_ip="", login_device="")

    def test_booking_page_parses_only_booking_models(self):
        response = xml("<Envelope><Body><QueryBookingDividPageResult>true</QueryBookingDividPageResult><containerModelList><BookingModel><innerBookingId>B-1</innerBookingId><dispBookingId>DISPLAY-1</dispBookingId><conActShipPackCnt>2</conActShipPackCnt></BookingModel></containerModelList><page><PagesCount>3</PagesCount></page></Body></Envelope>")
        with patch.object(soap, "_soap_call", return_value=response) as call:
            rows, pages = soap._booking_page(self.account, "B-1", 1)
        self.assertEqual((rows[0]["innerBookingId"], pages), ("B-1", 3))
        self.assertEqual(call.call_args.args[1], "QueryBookingDividPage")
        self.assertEqual(soap._value(call.call_args.args[2], "doNo"), "B-1")

    def test_detail_and_pack_parsing(self):
        booking_details = xml("<Envelope><QueryBookingDetailResult><PrePackingModel><innerContainerId>C-1</innerContainerId><dONo>DO-1</dONo><UsedpackNum>BOX-1</UsedpackNum></PrePackingModel></QueryBookingDetailResult></Envelope>")
        pack_page = xml("<Envelope><GetPackListByPageResult>true</GetPackListByPageResult><modelList><PackInfo><InnerPackNum>P-1</InnerPackNum><DispPackNum>BOX-1</DispPackNum><OrderNo>PO-1</OrderNo></PackInfo></modelList><page><PagesCount>1</PagesCount></page></Envelope>")
        with patch.object(soap, "_soap_call", side_effect=[booking_details, pack_page]):
            details = soap._booking_details(self.account, "B-1")
            packs, pages = soap._pack_page(self.account, "DO-1", "US", 1)
        self.assertEqual(details[0]["usedPackNum"], "BOX-1")
        self.assertEqual(details[0]["doNo"], "DO-1")
        self.assertEqual((packs[0]["innerPackNum"], pages), ("P-1", 1))

    def test_fault_is_rejected_without_exposing_server_detail(self):
        body = "<Envelope><Fault><faultstring>private detail</faultstring></Fault></Envelope>"
        response = types.SimpleNamespace(content=body.encode("utf-8"), text=body, raise_for_status=lambda: None)
        with patch.object(soap.requests, "post", return_value=response), self.assertRaises(soap.RfidError) as error:
            soap._soap_call(self.account, "QueryBookingDetail", xml("<Envelope/>"))
        self.assertEqual(error.exception.key, "error.soap_result")
        self.assertNotIn("private detail", str(error.exception))

    def test_service_url_normalizes_legacy_endpoint(self):
        self.assertEqual(soap._service_url("https://example.invalid/WebService"), "https://example.invalid/WebService.asmx")
        self.assertEqual(soap._service_url("https://example.invalid/"), "https://example.invalid/WebService.asmx")


if __name__ == "__main__":
    unittest.main()
