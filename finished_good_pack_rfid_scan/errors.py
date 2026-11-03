"""Stable error codes with catalog-backed messages."""

from finished_good_pack_rfid_scan.i18n import message


class RfidError(Exception):
    def __init__(self, key, status=400, **values):
        self.key = key
        self.status = status
        self.values = values
        super().__init__(message(key, **values))
