import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pulse_search_engine as eng
import pulse_search_p21 as p

class PolicyTests(unittest.TestCase):
    def test_three_origins_unique(self):
        self.assertEqual(len({x['origin'] for x in p.TARGETS}),3)
    def test_new_url_scope_exact(self):
        for t in p.TARGETS:
            self.assertEqual(eng.normal_url(t['url']),t['url'])
            self.assertEqual(eng.origin(t['url']),t['origin'])
    def test_existing_paths_not_wildcards(self):
        for t in p.TARGETS:
            self.assertNotIn('/',t['previous_paths'])
            self.assertTrue(all(x.startswith('/') for x in t['previous_paths']))
    def test_review_exact_bytes(self):
        q=Path(__file__).resolve().parents[1]/'owner_review_r2p20.json'
        self.assertEqual(p.sha256(q),p.REVIEW_SHA)
        self.assertEqual(len(p.verify_review(q)['questions']),12)
    def test_review_tampering_fails(self):
        with tempfile.TemporaryDirectory() as d:
            q=Path(d)/'bad.json';q.write_text('{}')
            with self.assertRaisesRegex(p.Hold,'human_review_sha256'):p.verify_review(q)
    def test_html_escaped(self):
        a=p.report_html({'status':'<script>x</script>','indexed_pages_after':14,'queries':[
          {'query':'<b>q</b>','coverage_status':'NO_INDEXED_MATCH','results':[]}]})
        self.assertNotIn('<script>',a);self.assertIn('&lt;script&gt;',a)

class OwnerFixture(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.db=self.root/'owner.sqlite'
        eng.initdb(self.db)
        sources=[]
        for t in p.TARGETS:
            sources.append({'source_id':t['source_id'],'origin':t['origin'],
                'allowed_paths':t['previous_paths'],'collection_approved':True,
                'display_mode':'metadata_only','rights_basis':'Fixture technical metadata research; no commercial rights.'})
        sources+= [
          {'source_id':'london_events_p14','origin':'https://www.london.gov.uk','allowed_paths':['/events/'],
           'collection_approved':True,'display_mode':'metadata_only','rights_basis':'Fixture technical metadata research; no commercial rights.'},
          {'source_id':'sqlite_sql','origin':'https://www.sqlite.org','allowed_paths':['/lang.html'],
           'collection_approved':True,'display_mode':'metadata_only','rights_basis':'Fixture technical metadata research; no commercial rights.'},
          {'source_id':'python_guide','origin':'https://docs.python.org','allowed_paths':['/3/tutorial/index.html'],
           'collection_approved':True,'display_mode':'metadata_only','rights_basis':'Fixture technical metadata research; no commercial rights.'},
          {'source_id':'robots_rfc','origin':'https://www.rfc-editor.org','allowed_paths':['/rfc/rfc9309.html'],
           'collection_approved':True,'display_mode':'metadata_only','rights_basis':'Fixture technical metadata research; no commercial rights.'}
        ]
        with eng.dbopen(self.db) as c:
            eng.register_sources(c,sources)
            c.execute('CREATE TABLE sitemap_candidates(source_id TEXT,url TEXT)')
            for i in range(112):c.execute('INSERT INTO sitemap_candidates VALUES(?,?)',('london_events_p14',f'https://www.london.gov.uk/events/item-{i}'))
            for idx,s in enumerate(sources):
                src=c.execute('SELECT * FROM sources WHERE source_id=?',(s['source_id'],)).fetchone()
                path=s['allowed_paths'][0]
                for j in range(2):
                    url=s['origin']+path+('' if j==0 else 'test'+str(j))
                    title=f'Fixture document {idx} {j}'
                    body=f'Document unique {idx} {j} test words'
                    eng.index_page(c,url,src,title,body,hashlib.sha256((title+body).encode()).hexdigest(),True)
        with sqlite3.connect(self.db) as c:c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.hash=p.sha256(self.db)
        self.review=Path(__file__).resolve().parents[1]/'owner_review_r2p20.json'
    def test_fixture_accepts_pinned_state(self):
        x=p.original_state(self.db,self.hash)
        self.assertEqual(x['baseline_pages'],14)
        self.assertEqual(x['sitemap_url_candidates'],112)
    def test_wrong_owner_hash_fails(self):
        with self.assertRaisesRegex(p.Hold,'sha256'):p.original_state(self.db,'0'*64)
    def test_source_change_exact(self):
        x=p.source_changes(p.original_state(self.db,self.hash))
        self.assertEqual(len(x),3)
        for item,new in zip(p.TARGETS,x):
            self.assertEqual(new['allowed_paths'][:-1],item['previous_paths'])
            self.assertEqual(new['allowed_paths'][-1],__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(item['url']).path)
            self.assertNotIn('/',new['allowed_paths'])
    def test_changed_policy_held(self):
        with eng.dbopen(self.db) as c:
            c.execute('UPDATE sources SET paths=? WHERE source_id=?',(json.dumps(['/']), 'uk_services'))
        with self.assertRaisesRegex(p.Hold,'previous_source_scope_changed'):p.original_state(self.db,p.sha256(self.db))
    def test_no_network_on_preflight(self):
        with patch.object(eng,'crawl',side_effect=AssertionError('network forbidden')):
            r=p.execute(self.db,self.review,self.root/'run',expected_sha=self.hash)
        self.assertEqual(r['status'],'READ_ONLY_PREFLIGHT_PASS_LIVE_PENDING')
        self.assertEqual(r['network_requests'],0)
        self.assertEqual(r['indexed_pages_after'],14)
        self.assertEqual(r['source_scope_extensions'],'NOT_APPLIED')
        self.assertEqual(p.sha256(self.db),self.hash)
    def test_preflight_report_writes_copy_only(self):
        r=p.execute(self.db,self.review,self.root/'out',expected_sha=self.hash)
        self.assertTrue((self.root/'out'/'expanded_research_index.sqlite').exists())
        self.assertTrue((self.root/'out'/'search_review.html').exists())
        self.assertEqual(len(r['queries']),6)
    def test_refuse_existing_output(self):
        with self.assertRaisesRegex(p.Hold,'output_directory_exists'):p.execute(self.db,self.review,self.root,expected_sha=self.hash)
    def test_live_mock_indexes_three_page_clone(self):
        def fake_crawl(db,source_config,seeds,**kwargs):
            self.assertEqual(set(seeds),{x['url'] for x in p.TARGETS})
            self.assertEqual(kwargs['max_depth'],0)
            self.assertEqual(kwargs['scheduled_urls'],seeds)
            self.assertFalse(kwargs['sitemaps'])
            cfg=json.loads(Path(source_config).read_text())
            self.assertEqual(len(cfg),3)
            with eng.dbopen(db) as c:
                for target in p.TARGETS:
                    src=c.execute('SELECT * FROM sources WHERE source_id=?',(target['source_id'],)).fetchone()
                    self.assertTrue(eng.scope(target['url'],src))
                    title='Research '+target['question']
                    body='This page explains '+target['question']
                    eng.index_page(c,target['url'],src,title,body,hashlib.sha256((title+body).encode()).hexdigest(),True)
            return {'fetch_requests':6,'outcomes':{'indexed':3}}
        with patch.object(eng,'crawl',side_effect=fake_crawl):
            r=p.execute(self.db,self.review,self.root/'live',True,self.hash)
        self.assertEqual(r['status'],'RESEARCH_CLONE_ALL_THREE_INDEXED_NOT_PRODUCTION')
        self.assertEqual(r['indexed_pages_after'],17)
        self.assertEqual(len(r['new_indexed_pages']),3)
        self.assertEqual(r['paid_search_provider_calls'],0)
        self.assertEqual(p.sha256(self.db),self.hash)
    def test_live_partial_is_hold(self):
        with patch.object(eng,'crawl',return_value={'fetch_requests':3,'outcomes':{'blocked':3}}):
            r=p.execute(self.db,self.review,self.root/'partial',True,self.hash)
        self.assertEqual(r['status'],'LIVE_PARTIAL_OR_NO_NEW_PAGES_HOLD')
        self.assertEqual(len(r['new_indexed_pages']),0)
    def test_seed_not_claimed_as_autodiscovery(self):
        r=p.execute(self.db,self.review,self.root/'independent',expected_sha=self.hash)
        self.assertIn('NOT Pulse sitemap-discovered',r['seed_provenance'])

if __name__=='__main__':unittest.main()
