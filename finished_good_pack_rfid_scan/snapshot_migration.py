"""Explicit, resumable storage maintenance. Schema migration never clears snapshots."""
import json
import hashlib
import os
from pathlib import Path
import frappe
from finished_good_pack_rfid_scan import scan_storage as storage

SCAN = "RFID Scan Detail"
JOB = "RFID Snapshot Migration"
NAME = "scan-storage-v1"


def authorize():
    if frappe.session.user == "Guest" or "System Manager" not in frappe.get_roles():
        frappe.throw("System Manager required", frappe.PermissionError)


def _job():
    if not frappe.db.exists(JOB, NAME):
        frappe.get_doc({"doctype": JOB, "name": NAME, "phase": "Ready"}).insert(ignore_permissions=True, set_name=NAME)
    return frappe.get_doc(JOB, NAME)


def _update(name, fields):
    frappe.db.set_value(SCAN, name, fields, update_modified=False)


def _checkpoint(job, **values):
    for k,v in values.items(): setattr(job,k,v)
    frappe.db.set_value(JOB, job.name, values, update_modified=False)
    frappe.db.commit()


def baseline():
    aggregate = frappe.db.sql("SELECT session, booking_id, order_no, do_no, disp_pack_num, is_metal_check, COUNT(*) AS n, MIN(scanned_at) AS earliest, MAX(scanned_at) AS latest FROM `tabRFID Scan Detail` GROUP BY session, booking_id, order_no, do_no, disp_pack_num, is_metal_check ORDER BY session, booking_id, order_no, do_no, disp_pack_num, is_metal_check", as_dict=True)
    return {
        "aggregate_digest": hashlib.sha256(json.dumps(aggregate,sort_keys=True,default=str).encode()).hexdigest(),
        "scan": frappe.db.sql("SELECT COUNT(*) AS rows_count, SUM(OCTET_LENGTH(payload)) AS payload_bytes FROM `tabRFID Scan Detail`", as_dict=True),
        "bookings": frappe.db.sql("SELECT COUNT(*) AS rows_count, SUM(OCTET_LENGTH(payload)) AS payload_bytes, SUM(COALESCE(JSON_LENGTH(JSON_EXTRACT(payload, '$.items')),0)=0) AS empty_items, SUM(COALESCE(JSON_LENGTH(JSON_EXTRACT(payload, '$.summaryRows')),0)=0) AS empty_summaries FROM `tabRFID Booking Snapshot`", as_dict=True),
    }


def run(stage="backfill", backup_path=None, retry=False, batch_size=1000):
    authorize()
    if stage not in ("backfill", "cleanup") or int(batch_size) not in range(1,1001): raise ValueError("Invalid stage/batch size")
    if not frappe.db.sql("SELECT GET_LOCK('fg_rfid_storage_v1',0)")[0][0]: raise RuntimeError("Another storage job is running")
    try:
        job = _job()
        if stage == "cleanup":
            backup = Path(backup_path or job.backup_path or "").resolve()
            backup_root = Path(frappe.get_site_path("private", "backups")).resolve()
            if backup_root not in backup.parents or not backup.is_file() or backup.stat().st_size == 0 or not str(backup).endswith(".sql.gz"):
                raise ValueError("A nonempty site database backup (.sql.gz) is required")
            _checkpoint(job, backup_path=str(backup))
        cursor_field = stage + "_cursor"
        if retry: _checkpoint(job, **{cursor_field: ""})
        if not job.report: _checkpoint(job, report=json.dumps({"before":baseline()},default=str))
        _checkpoint(job, phase=stage)
        while True:
            cursor = getattr(job,cursor_field) or ""
            rows = frappe.db.sql("SELECT * FROM `tabRFID Scan Detail` WHERE name>%s AND COALESCE(payload,'')!='' ORDER BY name LIMIT %s FOR UPDATE",(cursor,int(batch_size)),as_dict=True)
            if not rows: break
            verified = retained = cleaned = removed = added = 0
            originals = {}
            for row in rows:
                try:
                    original = json.loads(row.payload)
                    fields = storage.encode_scan(original,row)
                    if stage == "cleanup":
                        if row.storage_version != 1: raise ValueError("Backfill not verified")
                        restored = storage.decode_scan({**dict(row),"payload":None})
                        if storage.dump(original) != storage.dump(restored): raise ValueError("Persisted value mismatch")
                        # Only the raw JSON changes; RFID, timestamps and aggregate columns stay intact.
                        _update(row.name,{"payload":None,"storage_error":None})
                        cleaned += 1;removed += len(row.payload.encode("utf-8"))
                    else:
                        _update(row.name,{**fields,"storage_error":None})
                        originals[row.name] = original
                except (ValueError,TypeError,OverflowError) as error:
                    _update(row.name,{"storage_error":str(error)})
                    retained += 1
            if stage == "backfill" and originals:
                saved = frappe.get_all(SCAN,filters={"name":["in",list(originals)]},fields=["name",*storage.READ_FIELDS],limit_page_length=0)
                for row in saved:
                    try:
                        restored = storage.decode_scan({**dict(row),"payload":None})
                        if storage.dump(restored) != storage.dump(originals[row.name]): raise ValueError("Persisted value mismatch")
                        verified += 1
                        added += sum(len(str(row.get(f) or "").encode("utf-8")) for f in [*storage.NEW_FIELDS,"source_layout"])
                    except (ValueError,TypeError) as error:
                        _update(row.name,{"storage_version":0,"storage_error":str(error)})
                        retained += 1
                if len(saved) != len(originals): raise RuntimeError("Missing persisted rows")
            _checkpoint(job, **{cursor_field:rows[-1].name}, verified_rows=(job.verified_rows or 0)+verified,
                        retained_rows=(job.retained_rows or 0)+retained, cleaned_rows=(job.cleaned_rows or 0)+cleaned,
                        removed_json_bytes=(job.removed_json_bytes or 0)+removed, added_field_bytes=(job.added_field_bytes or 0)+added)
            print(json.dumps({"stage":stage,"cursor":rows[-1].name,"verified":verified,"retained":retained,"cleaned":cleaned}),flush=True)
        report=json.loads(job.report);report[stage+"_after"]=baseline()
        report["remaining_errors"] = frappe.db.sql("SELECT storage_error,COUNT(*) AS rows_count FROM `tabRFID Scan Detail` WHERE COALESCE(payload,'')!='' AND COALESCE(storage_error,'')!='' GROUP BY storage_error",as_dict=True)
        _checkpoint(job, phase=stage+" complete", report=json.dumps(report,default=str))
        return {"phase":job.phase,"verified":job.verified_rows,"retained_attempts":job.retained_rows,"cleaned":job.cleaned_rows,"removed_json_bytes":job.removed_json_bytes,"added_field_bytes":job.added_field_bytes,"report":report}
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.db.sql("SELECT RELEASE_LOCK('fg_rfid_storage_v1')")
