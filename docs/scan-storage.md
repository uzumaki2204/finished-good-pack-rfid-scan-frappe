# RFID scan storage v1 (0.1.44)

`RFID Scan Detail` stores source properties in explicit fields. `source_layout` is an append-only, position-based type/presence map defined by `scan_storage.FIELDS`: absent, null, string, integer, float, boolean remain distinct. `storage_version=1` identifies this representation. No ERP requests occur during conversion.

The source timestamp and source metal-check string are retained separately from the existing Datetime and Check fields. Legacy imports used Vietnam wall time truncated to seconds in `scanned_at`; the UTC source with fractional seconds remains verbatim in `source_scanned_at`. Neither value is rewritten. Other unexplained discrepancies block cleanup.

New writes verify the persisted fields and fall back to the original JSON for unknown keys, long values, unsupported types or conflicts. Readers support both formats. Booking Plan Snapshot is unchanged.

## Deployment and maintenance

1. Back up the site database. Deploy/migrate the schema and dual readers first. No schema migration clears data automatically.
2. As Administrator/System Manager, run `finished_good_pack_rfid_scan.snapshot_migration.run(stage="backfill")`. Batches of 1000 commit fields and cursor together. Check the `RFID Snapshot Migration` record `scan-storage-v1` and per-row `storage_error`.
3. Verify the round trip, reports, filters, historical APIs, new writes and aggregate digests on the site. Validate the database backup before cleanup.
4. Run the same function with `stage="cleanup", backup_path="/absolute/site/private/backups/database.sql.gz"`. It locks and re-verifies each row before clearing only `payload`. Unverified rows retain source JSON. It requires a nonempty site-local database backup.
5. Repeating either stage resumes from its cursor. Use `retry=True` to rescan retained/new fallback rows after addressing their errors. Counters are processing totals; the report records current row/byte totals and errors. Source records are never duplicated.

The maintenance lock prevents concurrent runs. Exceptions roll back the current batch; prior batches and checkpoints survive. Do not run OPTIMIZE TABLE automatically. Database files may retain reusable free space. Restore the backup to a separate site for recovery; do not overwrite newer production scans.

## Initial inventory (2026-11-13)

158,966 valid scan JSON objects, 27 source keys, 114,792,819 bytes. All rows passed lossless dry-run conversion after retaining the legacy timestamp representation. Added source-field contents plus layout estimated 34,197,057 bytes, excluding physical row/index overhead. All 195 existing Booking Snapshots had empty `items` and `summaryRows`; their 49,461 bytes were retained unchanged.

## Completed Dev migration (2026-11-13)

- Runtime 0.1.44 deployed and migrated through Pilot.
- Database backup created before conversion and validated with `gzip -t`.
- Backfilled and individually verified 158,966 rows; cleaned 158,966 duplicate JSON payloads; retained/error rows: 0.
- Removed JSON content: 114,792,819 bytes. Added source-field contents and layout: 34,197,057 bytes. Net content reduction: 80,595,762 bytes (76.86 MiB). These figures exclude row/index overhead and do not claim physical database file shrinkage.
- Aggregate digest before/backfill/cleanup unchanged: `bf360f583f41579f19047ff30fe4db0fb0c3da49d6f7aff44be15adfad6e1ab4`.
- Booking snapshots unchanged: 195 rows, 49,461 bytes. Their empty item/summary lists were recorded, not rebuilt from ERP.
- Post-cleanup: decoded all 158,966 records; verified a 11,712-row session history, eight simultaneous detail filters (12 results), last-page pagination (212 rows), and printed sampleCode/setCode/PO.
- Rollback-only live scenario verified structured new writes, persisted source round trip, repeated completion without duplicate rows, and unknown-field JSON fallback. No test sessions retained.
- Automated verification: 85 Python tests and 9 client refresh scenarios passed.
- Maintenance progress and baseline comparisons remain in the `RFID Snapshot Migration` record `scan-storage-v1`.
