import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pulse_search_engine as e
import pulse_search_p14 as p14
import pulse_search_p16 as p16

class P16Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name); self.db=self.root/'owner.sqlite'
        e.initdb(self.db)
        self.source={"source_id":"cityhall","origin":"https://www.london.gov.uk",
            "allowed_paths":["/events/"],"collection_approved":True,"display_mode":"metadata_only",
            "rights_basis":"Internal metadata research. Not a grant of commercial publication rights."}
        self.sources=self.root/'source.json';self.sources.write_text(json.dumps([self.source]))
        self.urls=['https://www.london.gov.uk/events/london-games-festival-2026',
                   'https://www.london.gov.uk/events/diwali-square-2026',
                   'https://www.london.gov.uk/events/city-hall-open-house-2026']
        self.mf=self.root/'manifest.json';self.write_manifest(self.urls)
        with e.dbopen(self.db) as c:
            e.register_sources(c,[self.source])
            c.executescript(p14.STAGE_SCHEMA)
            for url in self.urls:
                c.execute('INSERT INTO sitemap_candidates VALUES(?,?,?,?,?)',
                          ('cityhall',url,'https://www.london.gov.uk/sitemap.xml','2026-10-23',4))
            old='https://www.london.gov.uk/events/london-new-years-eve-2026'
            c.execute('INSERT INTO sitemap_candidates VALUES(?,?,?,?,?)',
                     ('cityhall',old,'https://www.london.gov.uk/sitemap.xml','2026-10-23',4))
            src=c.execute('SELECT * FROM sources WHERE source_id=?',('cityhall',)).fetchone()
            e.index_page(c,old,src,"London New Year's Eve 2026",
                         'Official London New Year Eve event details in London.',
                         'fixture_hash_baseline',True)
    def write_manifest(self,urls,**extra):
        self.mf.write_text(json.dumps({'source_id':'cityhall','purpose':'Internal research approved pages.','urls':urls,**extra}))
    def test_all_urls_were_discovered(self):
        p=p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
        self.assertEqual(p['staged_candidates'],4)
        self.assertEqual(len(p['approved_new_urls']),3)
    def test_no_network_prepare(self):
        before=p16.sha256(self.db)
        with patch('pulse_search_p16.engine.crawl',side_effect=AssertionError('must_not_crawl')):
            r=p16.execute(self.db,'cityhall',self.sources,self.mf,self.root/'audit')
        self.assertEqual(r['status'],'READ_ONLY_PREPARED_FOR_OPTIONAL_LIVE')
        self.assertEqual(r['baseline_indexed_pages'],1)
        self.assertEqual(r['indexed_pages_after'],1)
        self.assertEqual(r['network_requests'],0)
        self.assertEqual(p16.sha256(self.db),before)
        self.assertTrue((self.root/'audit'/'search_review.html').exists())
    def test_bounded_live_only_cloned_db(self):
        before=p16.sha256(self.db)
        def synthetic_crawl(db,source_json,seeds,**kwargs):
            self.assertEqual(seeds,self.urls)
            self.assertEqual(kwargs['max_depth'],0)
            self.assertEqual(kwargs['max_pages'],3)
            self.assertFalse(kwargs['sitemaps'])
            self.assertNotEqual(Path(db).resolve(),self.db.resolve())
            with e.dbopen(db) as c:
                src=c.execute('SELECT * FROM sources WHERE source_id=?',('cityhall',)).fetchone()
                for url in seeds[:2]:
                    e.index_page(c,url,src,url.rsplit('/',1)[-1].replace('-',' ').title(),
                                'Useful information about '+url.rsplit('/',1)[-1],
                                'sha_'+url[-20:],True)
            return {'fetch_requests':3,'outcomes':{'indexed':2,'removed_or_denied_404':1}}
        with patch('pulse_search_p16.engine.crawl',side_effect=synthetic_crawl) as spy:
            r=p16.execute(self.db,'cityhall',self.sources,self.mf,self.root/'audit',allow_live=True)
        self.assertEqual(spy.call_count,1)
        self.assertEqual(r['status'],'MULTIPAGE_COPY_INDEXED_INTERNAL_NOT_PRODUCTION')
        self.assertEqual(r['indexed_pages_after'],3)
        self.assertEqual(len(r['new_indexed_pages']),2)
        self.assertEqual(p16.sha256(self.db),before)
        self.assertEqual(r['paid_search_provider_calls'],0)
        self.assertEqual(len(r['search_evidence']),6)
    def test_unlisted_url_rejected(self):
        self.write_manifest([self.urls[0]+'-invented'])
        with self.assertRaisesRegex(p16.Hold,'catalog'):
            p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
    def test_cross_origin_hold(self):
        self.write_manifest(['https://example.com/events/x'])
        with self.assertRaises(p16.Hold):p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
    def test_foreign_source_hold(self):
        with self.assertRaisesRegex(Exception,'source'):
            p16.validate_plan(self.db,'wrong',self.sources,self.mf)
    def test_disabled_source_hold(self):
        with e.dbopen(self.db) as c:c.execute('UPDATE sources SET enabled=0')
        with self.assertRaisesRegex(Exception,'disabled'):
            p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
    def test_unlicensed_display_change_hold(self):
        d=dict(self.source);d['display_mode']='licensed_snippet';d['description_license_confirmed']=True
        self.sources.write_text(json.dumps([d]))
        with self.assertRaisesRegex(p16.Hold,'policy_mismatch'):
            p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
    def test_rights_policy_drift_hold(self):
        d=dict(self.source);d['rights_basis']='This is a different published rights basis; research only.'
        self.sources.write_text(json.dumps([d]))
        with self.assertRaisesRegex(p16.Hold,'policy_mismatch'):
            p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
    def test_duplicate_url_hold(self):
        self.write_manifest([self.urls[0],self.urls[0]])
        with self.assertRaisesRegex(p16.Hold,'count'):p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
    def test_fourth_url_hold(self):
        self.write_manifest(self.urls+[self.urls[0]])
        with self.assertRaisesRegex(p16.Hold,'count'):p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
    def test_unsafe_query_url_hold(self):
        u=self.urls[0]+'?token=xyz'
        with e.dbopen(self.db) as c:c.execute('INSERT INTO sitemap_candidates VALUES(?,?,?,?,?)',('cityhall',u,'x','2026',1))
        self.write_manifest([u])
        with self.assertRaisesRegex(p16.Hold,'query_url'):p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
    def test_output_already_exists_hold(self):
        with self.assertRaisesRegex(p16.Hold,'already_exists'):
            p16.execute(self.db,'cityhall',self.sources,self.mf,self.root)
    def test_no_commercial_mode(self):
        self.write_manifest(self.urls,publish=True)
        with self.assertRaisesRegex(p16.Hold,'manifest'):p16.validate_plan(self.db,'cityhall',self.sources,self.mf)
    def test_html_escaping(self):
        r={'status':'X','indexed_pages_after':1,'search_evidence':[{'query':'<bad>',
             'coverage_status':'NO_INDEXED_MATCH','results':[]}]}
        self.assertIn('&lt;bad&gt;',p16.html_report(r))
        self.assertNotIn('<bad>',p16.html_report(r))
    def test_db_original_hash_stable(self):
        old=p16.sha256(self.db)
        p16.copy_db_readonly(self.db,self.root/'clone.sqlite')
        self.assertEqual(old,p16.sha256(self.db))
        self.assertEqual(len(p16.indexed_snapshot(self.root/'clone.sqlite')),1)
    def test_db_output_exists_hold(self):
        p=self.root/'clone.sqlite';p.write_text('bad')
        with self.assertRaisesRegex(p16.Hold,'output_exists'):p16.copy_db_readonly(self.db,p)
    def test_wrong_year_page_rejected(self):
        self.assertFalse(p16.year_compatible('London New Years Eve 2027',
          {'title':'London New Years Eve 2026',
           'url':'https://www.london.gov.uk/events/london-new-years-eve-2026'}))
    def test_matching_year_page_admitted(self):
        self.assertTrue(p16.year_compatible('Diwali London 2026',
          {'title':'Diwali Square 2026','url':'https://www.london.gov.uk/events/diwali-square-2026'}))
    def test_yearless_result_never_auto_verified(self):
        self.assertTrue(p16.year_compatible('Diwali London 2026',
          {'title':'Diwali','url':'https://www.london.gov.uk/events/diwali-square'}))
    def test_no_preset_external_provider(self):
        self.assertFalse(any('brave' in x.lower() for x in p16.QUESTIONS))

if __name__=='__main__':unittest.main()
