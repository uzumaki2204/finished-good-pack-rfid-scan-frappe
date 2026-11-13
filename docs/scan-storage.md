# Current storage (0.1.47)

RFID Scan Detail uses explicit columns only. Scan Snapshot (`payload`) and Storage Conversion Error are removed from the DocType and physically dropped by migration. There is no JSON fallback. Unsupported input or a persisted round-trip mismatch rejects completion; the API rolls back the request.

Existing rows must already have storage_version=1 before the column-drop patch runs. The patch refuses unconverted rows. Booking plan snapshots remain unchanged.

System Manager and existing RFID Scan Manager permissions gain write access to their existing RFID DocTypes. Operator and Report Manager permissions remain unchanged. Visible source fields are editable; hidden storage metadata remains managed by code. Scan edits rebuild the source type map, normalize RFID, validate session ownership and update completed-session scan/metal totals. This does not enable Developer Mode or editing standard DocType definitions.

The following sections are historical records only and describe superseded formats/tools.

# RFID scan storage v1 (0.1.44)

`RFID Scan Detail` stores source properties in explicit fields. `source_layout` is an append-only, position-based type/presence map defined by `scan_storage.FIELDS`: absent, null, string, integer, float, boolean remain distinct. `storage_version=1` identifies this representation. No ERP requests occur during conversion.

The source timestamp and source metal-check string are retained separately from the existing Datetime and Check fields. Legacy imports used Vietnam wall time truncated to seconds in `scanned_at`; the UTC source with fractional seconds remains verbatim in `source_scanned_at`. Neither value is rewritten. Other unexplained discrepancies block cleanup.

New writes verify the persisted fields and fall back to the original JSON for unknown keys, long values, unsupported types or conflicts. Readers support both formats. Booking Plan Snapshot is unchanged.

## Production installation (0.1.45)

Fresh production installs do not create `RFID Snapshot Migration`. The one-time backfill/cleanup module and its DocType were removed from the package after Dev conversion. No data-conversion command is required for an empty site. Normal Frappe install/migrate remains necessary for schema, roles, routes and indexes.

`RFID Booking Snapshot` is required runtime data, not a migration log: it holds the session plan used by completion validation, refresh, recovery, unscanned-item comparison and reports. Keep it even on an initially empty site. Also keep `RFID Scan Session`, `RFID Scan Detail`, `RFID Session Photo` and `RFID SOAP Account`.

The legacy JSON reader and fallback remain to preserve unexpected source fields. New supported scan records use explicit fields directly. Existing Dev migration audit data is not automatically deleted; this release adds no destructive schema/data cleanup hook.

## Historical deployment and maintenance (0.1.44 only)

The commands below document the completed Dev operation, not instructions for a fresh production install. The migration tools are available in Git commit `563d38f` only; do not run them against 0.1.45. Sites with unconverted legacy data should complete and verify conversion with 0.1.44 before upgrading.

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

## 0.1.47 Dev verification (2026-11-13)

Pilot update `20261113-070053-518f97` completed with backup and site migration. Confirmed `payload` is absent from both DocType metadata and the SQL table. All 150,414 currently stored scan rows decode successfully; the site contains 195 sessions and 195 Booking snapshots.

Rollback-only live QA passed structured completion, duplicate completion idempotency, rejection of invalid RFID and unsupported ERP keys, preservation of unscanned plan items, filtered report reads, and ordinary Document.save() edits to sampleCode/setCode/market/metal status with session metal totals updated. Test transactions were rolled back. Automated checks: 81 Python tests plus client scan-queue and refresh scenarios passed.
