import sys
import types
import unittest
from io import BytesIO
from unittest.mock import patch, MagicMock

from PIL import Image

try:
    import frappe
except ImportError:
    sys.modules["frappe"] = types.ModuleType("frappe")

from finished_good_pack_rfid_scan import photos, service
from finished_good_pack_rfid_scan.image_processing import optimize, MAX_BYTES
from finished_good_pack_rfid_scan.errors import RfidError


def image_bytes(size=(48, 32), fmt="PNG", **kwargs):
    data = BytesIO()
    Image.new("RGB", size, "#2389bd").save(data, fmt, **kwargs)
    return data.getvalue()


class OptimizationTest(unittest.TestCase):
    def test_dimensions_format_and_no_upscale(self):
        for size, expected in [((2400, 1200), (2048, 1024)), ((1200, 2400), (1024, 2048)), ((48, 32), (48, 32))]:
            full, thumb, width, height = optimize(image_bytes(size))
            with Image.open(BytesIO(full)) as result, Image.open(BytesIO(thumb)) as thumbnail:
                self.assertEqual(result.format, "WEBP")
                self.assertEqual(result.size, expected)
                self.assertEqual((width, height), expected)
                self.assertLessEqual(max(thumbnail.size), 320)

    def test_orientation_and_metadata_removed(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "PRIVATE METADATA"
        full, _, width, height = optimize(image_bytes((60, 30), "JPEG", exif=exif))
        self.assertEqual((width, height), (30, 60))
        with Image.open(BytesIO(full)) as result:
            self.assertFalse(result.getexif())
            self.assertNotIn("icc_profile", result.info)
            self.assertNotIn("xmp", result.info)

    def test_transparency_retained(self):
        data = BytesIO()
        Image.new("RGBA", (5, 5), (255, 0, 0, 0)).save(data, "PNG")
        full, *_ = optimize(data.getvalue())
        with Image.open(BytesIO(full)) as result:
            self.assertEqual(result.getpixel((0, 0))[3], 0)

    def test_static_supported_formats(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            self.assertTrue(optimize(image_bytes(fmt=fmt))[0])

    def test_bad_content_and_unsupported_format(self):
        for data in (b"<svg>not an image</svg>", image_bytes(fmt="BMP"), image_bytes()[:30]):
            with self.assertRaises(RfidError) as error:
                optimize(data)
            self.assertEqual(error.exception.key, "error.photo_format")

    def test_animated_webp_rejected(self):
        data = BytesIO()
        Image.new("RGB", (10, 10), "red").save(data, "WEBP", save_all=True,
            append_images=[Image.new("RGB", (10, 10), "blue")], duration=100, loop=0)
        with self.assertRaises(RfidError):
            optimize(data.getvalue())

    def test_byte_and_pixel_limits(self):
        with self.assertRaises(RfidError) as error:
            optimize(b"x" * (MAX_BYTES + 1))
        self.assertEqual(error.exception.status, 413)
        with patch("finished_good_pack_rfid_scan.image_processing.MAX_PIXELS", 100):
            with self.assertRaises(RfidError) as error:
                optimize(image_bytes((11, 10)))
        self.assertEqual(error.exception.status, 413)


class PhotoPolicyTest(unittest.TestCase):
    def setUp(self):
        self.device = types.SimpleNamespace(name="D", company="C")
        self.session = types.SimpleNamespace(name="S", company="C", device="D", status="Completed")

    def test_session_rejects_wrong_company_device_and_deleted(self):
        for changes, status in [({"company": "OTHER"}, 404), ({"status": "Deleted"}, 404)]:
            session = types.SimpleNamespace(**{**vars(self.session), **changes})
            with patch.object(photos, "approved_device", return_value=self.device), \
                 patch.object(service.frappe, "db", types.SimpleNamespace(exists=lambda *_: True), create=True), \
                 patch.object(service.frappe, "get_doc", return_value=session, create=True):
                with self.assertRaises(RfidError) as error:
                    photos.authorize("D", "S")
            self.assertEqual(error.exception.status, status)

    def test_other_approved_company_device_can_read_upload_but_not_delete(self):
        self.session.device = "OTHER"
        for status in ("Active", "Completed"):
            self.session.status = status
            with patch.object(photos, "approved_device", return_value=self.device), \
                 patch.object(photos.frappe, "db", types.SimpleNamespace(exists=lambda *_: True, sql=lambda *_: None), create=True), \
                 patch.object(photos.frappe, "get_doc", return_value=self.session, create=True):
                self.assertEqual(photos.authorize("D", "S")[0], self.session)
                with self.assertRaises(RfidError):
                    photos.delete("D", "S", "P")
                with self.assertRaises(RfidError):
                    service._session("S", self.device)

    def test_unapproved_device_cannot_list(self):
        with patch.object(photos, "approved_device", side_effect=RfidError("error.device_pending", 403)):
            with self.assertRaises(RfidError):
                photos.list_photos("D", "S")

    def test_retry_returns_existing_without_processing_again(self):
        row = types.SimpleNamespace(name="P", deleted=0, original_name="a", width=1, height=1, byte_size=10, creation="now")
        with patch.object(photos, "authorize", return_value=(self.session, self.device)), \
             patch.object(photos.frappe, "db", types.SimpleNamespace(get_value=lambda *_: "P"), create=True), \
             patch.object(photos.frappe, "get_doc", return_value=row, create=True), \
             patch.object(photos, "optimize") as processor:
            result = photos.upload("D", "S", "ca31a034-b8f5-4c4c-9a91-e9ccc9c70965", None)
            self.assertEqual(result["id"], "P")
            processor.assert_not_called()
            row.deleted = 1
            with self.assertRaises(RfidError) as error:
                photos.upload("D", "S", "ca31a034-b8f5-4c4c-9a91-e9ccc9c70965", None)
            self.assertEqual(error.exception.status, 409)

    def test_completed_session_retry_does_not_write_scans_again(self):
        with patch.object(service, "approved_device", return_value=self.device), \
             patch.object(service, "_session", return_value=self.session), \
             patch.object(service, "_details", return_value={"sessionStatus": "Completed"}), \
             patch.object(service, "validate_scans") as validate:
            result = service.complete("D", "S", "", "", "", [])
        self.assertEqual(result["sessionStatus"], "Completed")
        validate.assert_not_called()

    def test_upload_stores_only_private_optimized_files(self):
        row = MagicMock(original_name="test.png", width=48, height=32, byte_size=100, creation="now")
        row.name = "P"
        row.insert.return_value = row
        files = []
        def make_doc(data):
            if data["doctype"] == photos.DOCTYPE:
                return row
            files.append(data)
            file = MagicMock()
            file.name = f"F{len(files)}"
            return file
        uploaded = types.SimpleNamespace(filename="test.png", stream=BytesIO(image_bytes()))
        with patch.object(photos, "authorize", return_value=(self.session, self.device)), \
             patch.object(photos.frappe, "db", types.SimpleNamespace(get_value=lambda *_: None), create=True), \
             patch.object(photos.frappe, "get_doc", side_effect=make_doc, create=True):
            photos.upload("D", "S", "ca31a034-b8f5-4c4c-9a91-e9ccc9c70965", uploaded)
        self.assertEqual(len(files), 2)
        for file in files:
            self.assertEqual(file["is_private"], 1)
            self.assertEqual(file["owner"], "Administrator")
            self.assertEqual(file["attached_to_name"], "P")
            with Image.open(BytesIO(file["content"])) as saved:
                self.assertEqual(saved.format, "WEBP")

    def test_photo_id_from_another_session_rejected(self):
        with patch.object(photos, "authorize"), \
             patch.object(photos.frappe, "db", types.SimpleNamespace(exists=lambda *_: True), create=True), \
             patch.object(photos.frappe, "get_doc", return_value=types.SimpleNamespace(session="OTHER", deleted=0), create=True):
            with self.assertRaises(RfidError):
                photos.get_photo("D", "S", "P")
            with self.assertRaises(RfidError):
                photos.delete("D", "S", "P")

    def test_delete_both_derivatives_and_keep_tombstone(self):
        row = MagicMock(session="S", deleted=0, image_file="F1", thumbnail_file="F2")
        row.name = "P"
        file = types.SimpleNamespace(attached_to_doctype=photos.DOCTYPE, attached_to_name="P")
        with patch.object(photos, "authorize"), \
             patch.object(photos.frappe, "db", types.SimpleNamespace(exists=lambda *_: True), create=True), \
             patch.object(photos.frappe, "get_doc", side_effect=[row, file, file], create=True), \
             patch.object(photos.frappe, "delete_doc", create=True) as delete:
            photos.delete("D", "S", "P")
            self.assertEqual(delete.call_count, 2)
            self.assertEqual(row.deleted, 1)
            self.assertIsNone(row.image_file)
            self.assertIsNone(row.thumbnail_file)

    def test_page_has_24_items_and_no_file_paths(self):
        rows = [types.SimpleNamespace(name=f"P{25-i:03}", original_name="a", width=1, height=1, byte_size=10, creation="now") for i in range(25)]
        with patch.object(photos, "authorize", return_value=(self.session,self.device)), patch.object(photos.frappe, "get_all", return_value=rows, create=True):
            result = photos.list_photos("D", "S")
        self.assertEqual(len(result["items"]), 24)
        self.assertEqual(result["nextCursor"], rows[23].name)
        self.assertNotIn("file_url", result["items"][0])


if __name__ == "__main__":
    unittest.main()
