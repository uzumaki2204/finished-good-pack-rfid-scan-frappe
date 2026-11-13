import json
import types
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import test_scan_storage as fixtures
from finished_good_pack_rfid_scan import snapshot_migration as m, scan_storage as st


class Row(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class MigrationTests(unittest.TestCase):
    def setup_run(self, source=None):
        fixture=fixtures.ScanStorageTests();source=source or fixture.sample()
        row=Row(**fixture.row(),name="S1",payload=json.dumps(source),storage_version=0)
        job=types.SimpleNamespace(name="JOB",phase="Ready",backfill_cursor="",cleanup_cursor="",report="",verified_rows=0,retained_rows=0,cleaned_rows=0,removed_json_bytes=0,added_field_bytes=0)
        db=MagicMock()
        def sql(query,*args,**kwargs):
            if "GET_LOCK" in query:return [(1,)]
            if "SELECT *" in query:return [row] if not job.backfill_cursor else []
            return []
        db.sql.side_effect=sql
        db.set_value.side_effect=lambda dt,name,fields,**kw: row.update(fields)
        def checkpoint(j,**values):
            for k,v in values.items():setattr(j,k,v)
        patches=[patch.object(m,"authorize"),patch.object(m.frappe,"get_site_path",return_value="/site/private/backups",create=True),patch.object(m,"_job",return_value=job),patch.object(m,"_checkpoint",side_effect=checkpoint),patch.object(m,"baseline",return_value={}),patch.object(m.frappe,"db",db,create=True),patch.object(m.frappe,"get_all",side_effect=lambda *a,**kw:[row.copy()],create=True)]
        # get_all returns Frappe-style dictionaries with attribute access.
        patches[-1]=patch.object(m.frappe,"get_all",side_effect=lambda *a,**kw:[Row(row)],create=True)
        for p in patches:p.start();self.addCleanup(p.stop)
        return row,job,db

    def test_backfill_verifies_and_keeps_original_until_cleanup(self):
        row,job,db=self.setup_run()
        original=row.payload
        result=m.run()
        self.assertEqual(result["verified"],1)
        self.assertEqual(row.payload,original)
        self.assertEqual(st.dump(st.decode_scan({**row,"payload":None})),st.dump(json.loads(original)))
        self.assertEqual(job.backfill_cursor,"S1")
        m.run()
        self.assertEqual(job.verified_rows,1)

    def test_unknown_keys_keep_original_and_record_reason(self):
        row,job,db=self.setup_run({**fixtures.ScanStorageTests().sample(),"future":"data"})
        m.run()
        self.assertEqual(row.storage_version,0)
        self.assertIn("future",row.storage_error)
        self.assertTrue(row.payload)
        self.assertEqual(job.retained_rows,1)

    def test_database_failure_rolls_back_current_batch(self):
        row,job,db=self.setup_run()
        db.set_value.side_effect=RuntimeError("write failed")
        with self.assertRaises(RuntimeError):m.run()
        db.rollback.assert_called_once()
        self.assertEqual(job.backfill_cursor,"")

    def test_second_runner_is_rejected(self):
        row,job,db=self.setup_run()
        db.sql.return_value=[(0,)];db.sql.side_effect=None
        with self.assertRaises(RuntimeError):m.run()
        db.set_value.assert_not_called()

    def test_cleanup_rechecks_persisted_values_and_preserves_corruption(self):
        row,job,db=self.setup_run()
        row.update(st.encode_scan(json.loads(row.payload),row))
        row["warehouse"]="corrupted"
        with tempfile.TemporaryDirectory() as folder:
            backup=Path(folder)/"db.sql.gz";backup.write_bytes(b"test backup fixture")
            with patch.object(m.frappe,"get_site_path",return_value=folder):
                def sql(query,*args,**kwargs):
                    if "GET_LOCK" in query:return [(1,)]
                    if "SELECT *" in query:return [row] if not job.cleanup_cursor else []
                    return []
                db.sql.side_effect=sql
                m.run(stage="cleanup",backup_path=str(backup))
        self.assertTrue(row.payload)
        self.assertIn("mismatch",row.storage_error)
        self.assertEqual(job.cleaned_rows,0)

    def test_cleanup_requires_real_backup(self):
        row,job,db=self.setup_run()
        with self.assertRaises(ValueError):m.run(stage="cleanup",backup_path="/nonexistent.sql.gz")
        self.assertTrue(row.payload)

if __name__=="__main__":unittest.main()
