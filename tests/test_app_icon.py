import sys
import types
import unittest
from unittest.mock import patch


try:
    import frappe
except ImportError:
    frappe = types.ModuleType("frappe")
    sys.modules["frappe"] = frappe

from finished_good_pack_rfid_scan import access


class AppIconTest(unittest.TestCase):
    def test_all_signed_in_desk_users_see_shortcut(self):
        for user in ("Administrator", "operator@example.invalid"):
            with self.subTest(user=user), patch.object(access.frappe, "session", types.SimpleNamespace(user=user), create=True):
                self.assertTrue(access.can_open())

    def test_guest_does_not_see_desk_shortcut(self):
        with patch.object(access.frappe, "session", types.SimpleNamespace(user="Guest"), create=True):
            self.assertFalse(access.can_open())


if __name__ == "__main__":
    unittest.main()
