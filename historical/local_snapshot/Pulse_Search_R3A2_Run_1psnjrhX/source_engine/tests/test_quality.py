import json
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pulse_search_engine as e
import pulse_search_scheduler as s
import pulse_search_quality as q

class Quality(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'index.sqlite'
        e.initdb(self.db);s.init_schedule(self.db)
        src={'source_id':'demo','origin':'https://docs.example.org','allowed_paths':['/manual/'],
             'collection_approved':True,'display_mode':'metadata_only',
             'rights_basis':'Local test source, no network requests, metadata only.'}
        with e.dbopen(self.db) as conn:
            e.register_sources(conn,[src])
            self.row=conn.execute('SELECT * FROM sources').fetchone()
            url='https://docs.example.org/manual/index.html'
            body='Pulse Search operates a secure independent crawler and index for developer reference.'
            title='Independent Search Manual'
            h=hashlib.sha256((title+'\n'+body).encode()).hexdigest()
            e.index_page(conn,url,self.row,title,body,h,True)
            e.enqueue(conn,url,self.row,0)
        s.sync(self.db)
    def test_read_only_protection(self):
        with q.readonly(self.db) as conn:
            with self.assertRaises(sqlite3.DatabaseError):conn.execute('DELETE FROM pages')
    def test_index_audit_pass(self):
        a=q.audit(self.db)
        self.assertEqual(a['status'],'PASS')
        self.assertEqual(a['counts']['indexed_pages'],1)
        self.assertEqual(a['counts']['active_sources'],1)
    def test_audit_no_body_export(self):
        a=q.audit(self.db)
        self.assertNotIn('operates a secure independent crawler',json.dumps(a))
    def test_audit_finds_missing_fts(self):
        with e.dbopen(self.db) as c:c.execute('DELETE FROM page_fts')
        self.assertEqual(q.audit(self.db)['status'],'HOLD')
    def test_audit_finds_extra_fts(self):
        with e.dbopen(self.db) as c:c.execute('INSERT INTO page_fts(rowid,title,body) VALUES(999,?,?)',('bad','unrelated'))
        self.assertIn('orphan_fts_row:999',q.audit(self.db)['errors'])
    def test_audit_detects_fts_content_mismatch(self):
        with e.dbopen(self.db) as c:c.execute("UPDATE page_fts SET title='wrong' WHERE rowid=1")
        self.assertIn('fts_content_mismatch:1',q.audit(self.db)['errors'])
    def test_audit_finds_corrupt_body(self):
        with e.dbopen(self.db) as c:c.execute("UPDATE pages SET body='tampered' WHERE id=1")
        self.assertIn('stored_content_hash_mismatch:1',q.audit(self.db)['errors'])
    def test_audit_finds_indexed_duplicate(self):
        with e.dbopen(self.db) as c:c.execute("UPDATE pages SET duplicate_of='https://docs.example.org/manual/copy' WHERE id=1")
        self.assertIn('duplicate_indexed:1',q.audit(self.db)['errors'])
    def test_retired_source_removed(self):
        e.retire_source(self.db,'demo')
        self.assertEqual(q.audit(self.db)['status'],'PASS')
        self.assertEqual(q.audit(self.db)['counts']['indexed_pages'],0)
    def test_retired_source_with_retained_page_detected(self):
        with e.dbopen(self.db) as c:c.execute("UPDATE sources SET approved=0,enabled=0 WHERE source_id='demo'")
        self.assertTrue(any('retired_or_unapproved' in m for m in q.audit(self.db)['errors']))
    def test_scope_out_of_bounds(self):
        with e.dbopen(self.db) as c:c.execute("UPDATE pages SET url='https://docs.example.org/admin' WHERE id=1")
        self.assertTrue(any('page_outside' in m for m in q.audit(self.db)['errors']))
    def test_eval_hits_expected_source(self):
        r=q.evaluate(self.db,[{'q':'independent search','expected_source_id':'demo'}])
        self.assertEqual(r['expected_source_hit_at_10'],1.0)
        self.assertGreaterEqual(r['total_queries'],1)
    def test_eval_misses_unavailable_phrase(self):
        r=q.evaluate(self.db,[{'q':'nothingatall','expected_source_id':'demo'}])
        self.assertEqual(r['expected_source_hit_at_10'],0.0)
    def test_eval_not_claimed_web_scale(self):
        r=q.evaluate(self.db,[{'q':'search'}])
        self.assertIn('not internet search',r['scope'])
    def test_eval_rejects_excessive_probes(self):
        with self.assertRaises(ValueError):q.evaluate(self.db,[{'q':'a'}]*31)
    def test_eval_rejects_repeats(self):
        with self.assertRaises(ValueError):q.evaluate(self.db,[{'q':'search'}],21)
    def test_eval_no_body_export(self):
        x=q.evaluate(self.db,[{'q':'independent search'}])
        self.assertNotIn('operates a secure independent crawler',json.dumps(x))
    def test_freshness_timestamp(self):
        with e.dbopen(self.db) as c:c.execute("UPDATE pages SET fetched_at='INVALID' WHERE id=1")
        self.assertIn('invalid_fetched_at:1',q.audit(self.db)['errors'])
    def test_query_report_speed_is_measured(self):
        a=q.evaluate(self.db,[{'q':'crawler'}],repeats=4)
        self.assertGreaterEqual(a['latency_ms']['p95'],0)
    def test_invisible_fts_unindexed_row_detected(self):
        with e.dbopen(self.db) as c:c.execute('UPDATE pages SET indexed=0 WHERE id=1')
        self.assertIn('fts_row_mismatch:1',q.audit(self.db)['errors'])

if __name__=='__main__': unittest.main()
