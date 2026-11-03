"""Complete app-owned DocType indexes and navigation during Pilot migration."""


def execute():
    from finished_good_pack_rfid_scan.install import after_migrate

    after_migrate()
