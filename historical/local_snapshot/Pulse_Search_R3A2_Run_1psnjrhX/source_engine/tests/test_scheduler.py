import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import threading
import http.server
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pulse_search_engine as e
import pulse_search_scheduler as s
import test_engine as base

class Scheduling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),base.Fixture)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
        cls.server2=http.server.ThreadingHTTPServer(('127.0.0.1',0),base.Fixture)
        cls.thread2=threading.Thread(target=cls.server2.serve_forever,daemon=True)
        cls.thread2.start()
        cls.url2=f'http://127.0.0.1:{cls.server2.server_port}'
    @classmethod
    def tearDownClass(cls):
        for srv,th in [(cls.server,cls.thread),(cls.server2,cls.thread2)]:
            srv.shutdown();th.join();srv.server_close()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'index.sqlite';e.initdb(self.db);s.init_schedule(self.db)
        self.source={'source_id':'first','origin':self.url,'allowed_paths':['/'],
            'collection_approved':True,'display_mode':'metadata_only',
            'rights_basis':'Locally controlled fixture authorises scoped test indexing.'}
        self.file=Path(self.tmp.name)/'sources.json';self.file.write_text(json.dumps([self.source]))
        base.Fixture.hits=[];base.Fixture.robot_status=200
        base.Fixture.refresh_version=1;base.Fixture.refresh_gone=False
        base.Fixture.refresh_noindex=False;base.Fixture.refresh_robots_block=False
    def seed(self,paths=['/guide']):
        return s.seed(self.db,self.file,[self.url+p for p in paths],allow_local=True)
    def cycle(self,**kwargs):
        return s.run_cycle(self.db,self.file,min_delay=0,max_pages=1,max_per_source=1,allow_local=True,**kwargs)
    def test_version(self):self.assertIn('r2p4',s.VERSION)
    def test_init_stats(self):
        self.assertEqual(s.summary(self.db)['total'],0)
    def test_seed_identifiers(self):
        x=self.seed(['/guide','/refresh'])
        self.assertEqual(x['new_frontier_urls'],2)
        self.assertEqual(s.summary(self.db)['ready_due'],2)
    def test_duplicate_seed_no_repeat(self):
        self.seed();self.assertEqual(self.seed()['new_frontier_urls'],0)
        self.assertEqual(s.summary(self.db)['total'],1)
    def test_scope_reject(self):
        with self.assertRaises(e.Hold):s.seed(self.db,self.file,['https://example.org/'],True)
    def test_missing_rights(self):
        self.source['rights_basis']='not verified';self.file.write_text(json.dumps([self.source]))
        with self.assertRaises(e.Hold):self.seed()
    def test_claim_bounds(self):
        self.seed()
        with self.assertRaises(e.Hold):s.claim(self.db,0)
        with self.assertRaises(e.Hold):s.claim(self.db,5,0)
        with self.assertRaises(e.Hold):s.claim(self.db,1,1,60)
    def test_live_fixture_cycle_indexes(self):
        self.seed();r=self.cycle()
        self.assertEqual(r['selected_urls'],1)
        self.assertEqual(r['crawl']['outcomes'].get('indexed'),1)
        with e.dbopen(self.db) as c:self.assertEqual(len(e.search(c,'independent crawling')),1)
    def test_immediate_repeat_idle(self):
        self.seed();self.cycle()
        self.assertEqual(self.cycle()['selected_urls'],0)
    def test_future_revisit_after_due(self):
        self.seed();self.cycle()
        with e.dbopen(self.db) as c:
            self.assertEqual(c.execute('SELECT state FROM scheduled_urls').fetchone()[0],'ready')
            c.execute('UPDATE scheduled_urls SET next_due=?',(s.stamp(s.now_utc()-timedelta(hours=1)),))
        r=self.cycle()
        self.assertEqual(r['crawl']['outcomes'].get('not_modified_304',0),0)
        self.assertEqual(r['crawl']['outcomes'].get('unchanged_content',0),1)
    def test_link_discovery_automatically_scheduled(self):
        self.seed(['/'])
        r=self.cycle()
        self.assertGreaterEqual(r['newly_discovered_urls'],1)
        self.assertGreaterEqual(s.summary(self.db)['ready_due'],1)
    def test_does_not_process_other_unclaimed(self):
        self.seed(['/guide','/refresh'])
        r=self.cycle();self.assertEqual(r['selected_urls'],1)
        self.assertEqual(r['crawl']['processed_pages'],1)
        self.assertEqual(s.summary(self.db)['ready_due'],1)
    def test_refuse_second_worker(self):
        self.seed();claimed=s.claim(self.db,1,1)
        with self.assertRaises(e.Hold):s.claim(self.db,1,1)
        s.finish(self.db,claimed,failed=True)
        self.assertEqual(s.summary(self.db)['states']['ready'],1)
    def test_crash_recovery_expired_lease(self):
        self.seed();claimed=s.claim(self.db,1,1)
        past=s.stamp(s.now_utc()-timedelta(hours=1))
        with e.dbopen(self.db) as c:
            c.execute("UPDATE scheduler_lock SET expires=?",(past,))
            c.execute("UPDATE scheduled_urls SET lease_until=?,next_due=?",(past,past))
        new=s.claim(self.db,1,1)
        self.assertEqual(new['urls'],claimed['urls'])
        s.finish(self.db,new,failed=True)
    def test_transient_error_backoff(self):
        self.seed();base.Fixture.robot_status=503
        r=self.cycle()
        self.assertEqual(r['selected_urls'],1)
        with e.dbopen(self.db) as c:
            row=c.execute('SELECT state, failures,next_due,last_outcome FROM scheduled_urls').fetchone()
            self.assertEqual(row['state'],'ready')
            self.assertEqual(row['failures'],1)
            self.assertTrue(row['last_outcome'].startswith('hold:robots_http_503'))
            self.assertGreater(datetime.fromisoformat(row['next_due']),s.now_utc())
    def test_permanent_robots_pause(self):
        self.seed(['/blocked']);self.cycle()
        self.assertEqual(s.summary(self.db)['states']['paused'],1)
        self.assertEqual(self.cycle()['selected_urls'],0)
    def test_404_pause(self):
        self.seed(['/404']);self.cycle()
        self.assertEqual(s.summary(self.db)['states']['paused'],1)
    def test_rights_retire_withdraws_from_scheduler(self):
        self.seed();self.cycle()
        self.assertEqual(e.retire_source(self.db,'first'),1)
        self.assertEqual(s.summary(self.db)['total'],0)
        self.assertEqual(self.cycle()['selected_urls'],0)
    def test_two_sources_fair_select(self):
        other=dict(self.source,source_id='second',origin=self.url2)
        self.file.write_text(json.dumps([self.source,other]))
        s.seed(self.db,self.file,[self.url+'/guide',self.url2+'/guide'],True)
        r=s.run_cycle(self.db,self.file,max_pages=2,max_per_source=1,min_delay=0,allow_local=True)
        self.assertEqual(r['selected_urls'],2)
        self.assertEqual(r['crawl']['processed_pages'],2)
    def test_no_provider_api_calls(self):
        self.seed();r=self.cycle()
        self.assertEqual(r['paid_search_api_requests'],0)
        self.assertEqual(r['external_search_engine_calls'],0)
    def test_refresh_budget_enforced(self):
        self.seed()
        with self.assertRaises(e.Hold):self.cycle(refresh_hours=0)
    def test_empty_cycle_unlocks(self):
        self.seed();self.cycle();self.cycle()
        with e.dbopen(self.db) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM scheduler_lock').fetchone()[0],0)

    def test_cooldown_blocks_even_due_url(self):
        self.seed(['/guide','/refresh'])
        token=s.claim(self.db,1,1)
        s.finish(self.db,token,failed=True,min_delay=90)
        self.assertEqual(s.summary(self.db)['claimable_due'],0)
        with e.dbopen(self.db) as c:
            c.execute('UPDATE scheduled_urls SET next_due=?',
                      (s.stamp(s.now_utc()-timedelta(seconds=2)),))
        self.assertEqual(s.summary(self.db)['claimable_due'],0)
    def test_cooldown_expires(self):
        self.seed(['/guide','/refresh'])
        token=s.claim(self.db,1,1)
        s.finish(self.db,token,failed=True,min_delay=90)
        with e.dbopen(self.db) as c:
            ts=s.stamp(s.now_utc()-timedelta(seconds=1))
            c.execute('UPDATE origin_cooldown SET next_eligible=?',(ts,))
            c.execute('UPDATE scheduled_urls SET next_due=?',(ts,))
        self.assertEqual(s.summary(self.db)['claimable_due'],2)
    def test_robots_delay_carried_across_cycles(self):
        self.seed(['/guide','/refresh'])
        first=s.claim(self.db,1,1)
        mock={'effective_origin_delays':{self.url:240}}
        s.finish(self.db,first,mock,min_delay=1)
        with e.dbopen(self.db) as c:
            row=c.execute('SELECT next_eligible FROM origin_cooldown').fetchone()
            self.assertGreater(datetime.fromisoformat(row[0]),s.now_utc()+timedelta(seconds=220))
    def test_restart_persistent(self):
        self.seed()
        before=s.summary(self.db)
        s.init_schedule(self.db)
        self.assertEqual(s.summary(self.db)['total'],before['total'])
    def test_bounded_loop_grows_index(self):
        self.seed(['/guide','/refresh'])
        report=s.run_bounded_loop(self.db,self.file,cycles=2,interval_seconds=0,
                       max_pages=1,max_per_source=1,min_delay=0,allow_local=True)
        self.assertEqual(report['completed_cycles'],2)
        self.assertEqual(report['total_selected'],2)
        with e.dbopen(self.db) as c:self.assertGreaterEqual(e.stats(c)['indexed_pages'],2)
    def test_no_unbounded_loop(self):
        with self.assertRaises(e.Hold):s.run_bounded_loop(self.db,self.file,cycles=0)
        with self.assertRaises(e.Hold):s.run_bounded_loop(self.db,self.file,cycles=21)
        with self.assertRaises(e.Hold):s.run_bounded_loop(self.db,self.file,cycles=2,interval_seconds=0)

if __name__=='__main__':unittest.main()
