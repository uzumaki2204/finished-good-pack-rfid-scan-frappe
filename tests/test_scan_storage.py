import copy
import json
import unittest
from datetime import datetime
from finished_good_pack_rfid_scan import scan_storage as s


class ScanStorageTests(unittest.TestCase):
    def sample(self):
        return {"finishedGoodPackDetailId":"D", "rfid":"RFID", "bookingId":"B", "orderNo":"P", "doNo":"DO", "itemCode":"I", "dispPackNum":"00001", "isMetalCheck":"Y", "scannedAtUtc":"2026-11-13T08:00:00.123+07:00", "qtyPerSet":16, "quantity":0, "sampleCode":"07217H060C", "setCode":"32-004-000", "warehouse":"Kho Việt Nam"}

    def row(self):
        return {"detail_id":"D", "rfid":"RFID", "booking_id":"B", "order_no":"P", "do_no":"DO", "item_code":"I", "disp_pack_num":"00001", "is_metal_check":1, "scanned_at":datetime(2026,11,13,1,0,0,123000)}

    def test_lossless_all_supported_keys(self):
        source=self.sample()
        for key in s.FIELDS:
            if key not in source: source[key]="Giá trị nguồn"
        row=self.row();fields=s.encode_scan(source,row)
        self.assertEqual(s.dump(s.decode_scan({**row,**fields})),s.dump(source))
        self.assertEqual(fields["sample_code"],"07217H060C")
        self.assertEqual(fields["set_code"],"32-004-000")
        self.assertEqual(fields["source_scanned_at"],source["scannedAtUtc"])

    def test_exact_missing_null_empty_numeric_and_boolean_types(self):
        for value in (None,"",0,1,False,True,1.25,"0016",9007199254740993):
            source=self.sample();source["quantity"]=value
            row=self.row();fields=s.encode_scan(source,row)
            actual=s.decode_scan({**row,**fields})
            self.assertEqual(type(actual["quantity"]),type(value))
            self.assertEqual(actual["quantity"],value)
            self.assertNotIn("marketName",actual)

    def test_unknown_nested_long_and_conflicts_keep_json(self):
        for changes in ({"unknownField":"keep me"},{"warehouse":"x"*256},{"quantity":{"nested":1}},{"rfid":"OTHER"},{"scannedAtUtc":"2026-11-13T09:00:00+07:00"},{"isMetalCheck":"N"}):
            source={**self.sample(),**changes}
            fields=s.new_scan_fields(source,self.row())
            self.assertEqual(fields["storage_version"],0)
            self.assertEqual(json.loads(fields["payload"]),source)

    def test_legacy_local_time_column_and_source_milliseconds_both_survive(self):
        source=self.sample();row=self.row();row["scanned_at"]=datetime(2026,11,13,8,0,0)
        encoded=s.encode_scan(source,row)
        self.assertEqual(s.decode_scan({**row,**encoded})["scannedAtUtc"],source["scannedAtUtc"])
        self.assertEqual(row["scanned_at"],datetime(2026,11,13,8,0,0))

    def test_bad_payload_not_silently_replaced(self):
        with self.assertRaises(ValueError): s.decode_scan({"payload":"broken"})
        with self.assertRaises(ValueError): s.decode_scan({"payload":None,"storage_version":0})

    def test_legacy_payload_and_new_fields_produce_identical_response(self):
        source=self.sample();row=self.row();fields=s.encode_scan(source,row)
        self.assertEqual(s.decode_scan({"payload":json.dumps(source)}),s.decode_scan({**row,**fields}))

    def test_database_corruption_fails_verification(self):
        source=self.sample();row=self.row();fields=s.encode_scan(source,row)
        actual=s.decode_scan({**row,**fields,"warehouse":"truncated"})
        self.assertNotEqual(s.dump(actual),s.dump(source))

    def test_filter_uses_columns_and_legacy_fallback(self):
        expression=s.field_sql("sampleCode")
        self.assertIn("storage_version=1",expression)
        self.assertIn("`sample_code`",expression)
        self.assertIn("$.sampleCode",expression)

if __name__=="__main__":unittest.main()
