import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "finished_good_pack_rfid_scan"


class ContractTest(unittest.TestCase):
    def test_catalogs_have_identical_keys_and_all_references_exist(self):
        catalog = json.loads((PACKAGE / "i18n.json").read_text(encoding="utf-8"))
        self.assertEqual(set(catalog["vi"]), set(catalog["en"]))
        references = set()
        for path in PACKAGE.rglob("*"):
            if path.suffix not in (".py", ".js", ".html"):
                continue
            source = path.read_text(encoding="utf-8")
            references.update(re.findall(r"(?:message|notice|text|data-i18n)=?\(?(?:\s*[\"'])([a-z]+\.[a-z_]+)", source))
            references.update(re.findall(r'data-i18n="([a-z]+\.[a-z_]+)"', source))
        self.assertFalse(references - set(catalog["vi"]), references - set(catalog["vi"]))

    def test_doctypes_are_in_separate_module_and_have_field_order(self):
        for path in (PACKAGE / "finished_good_pack_rfid_scan" / "doctype").glob("*/*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["module"], "Finished Good Pack RFID Scan")
            self.assertEqual(data["field_order"], [row["fieldname"] for row in data["fields"]])
        self.assertEqual((PACKAGE / "modules.txt").read_text(encoding="utf-8").strip(), "Finished Good Pack RFID Scan")

    def test_no_custom_css_or_secret_in_packaged_assets(self):
        self.assertEqual(list(PACKAGE.rglob("*.css")), [])
        html = (PACKAGE / "templates" / "includes" / "tablet_head.html").read_text(encoding="utf-8")
        self.assertIn("desk.bundle.css", html)
        self.assertNotIn("site.css", html)
        patches = (PACKAGE / "patches.txt").read_text(encoding="utf-8")
        self.assertIn("[pre_model_sync]", patches)
        self.assertIn("[post_model_sync]", patches)
        self.assertIn("v0_1_0_setup", patches)


if __name__ == "__main__":
    unittest.main()
