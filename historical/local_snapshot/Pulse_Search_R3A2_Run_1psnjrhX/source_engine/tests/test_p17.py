import json
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pulse_search_engine as e
import pulse_search_p14 as p14
import pulse_search_p17 as p17
import pulse_search_real_questions as r9


def source(sid,origin,paths):
    return {'source_id':sid,'origin':origin,'allowed_paths':paths,'collection_approved':True,
            'display_mode':'metadata_only','rights_basis':'Internal technical research only; no commercial publication allowed.'}


def add(c,url,sid,title):
    src=c.execute('SELECT * FROM sources WHERE source_id=?',(sid,)).fetchone()
    body=f'Authoritative research content about {title}, with enough text to index for testing.'
    rawhash=hashlib.sha256((title+'\n'+body).encode()).hexdigest()
    e.index_page(c,url,src,title,body,rawhash,True)


class P17Tests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name); self.p16=self.root/'p16.sqlite';self.p12=self.root/'p12.sqlite'
        e.initdb(self.p16);e.initdb(self.p12)
        self.city=source('london_events_p14','https://www.london.gov.uk',['/events/'])
        self.p12_sources=[source('london_nye','https://www.london.gov.uk',['/media-centre/']),
            source('uk_services','https://www.gov.uk',['/renew-adult-passport','/register-to-vote']),
            source('nhs_services','https://www.nhs.uk',['/nhs-services/']),
            source('mdn_http','https://developer.mozilla.org',['/en-US/docs/Web/HTTP'])]
        with e.dbopen(self.p16) as c:
            e.register_sources(c,[self.city]);c.executescript(p14.STAGE_SCHEMA)
            for url in sorted(p17.CITY_PAGES):
                add(c,url,'london_events_p14',url.rsplit('/',1)[-1].replace('-',' ').title())
            urls=sorted(p17.CITY_PAGES)+[f'https://www.london.gov.uk/events/fixture-item-{i}' for i in range(108)]
            for u in urls:
                c.execute('INSERT INTO sitemap_candidates VALUES(?,?,?,?,?)',('london_events_p14',u,'https://www.london.gov.uk/sitemap.xml?page=2','2026-10-23',5))
        self.passport='https://www.gov.uk/renew-adult-passport/renew'
        with e.dbopen(self.p12) as c:
            e.register_sources(c,self.p12_sources)
            add(c,'https://www.london.gov.uk/media-centre/press-release','london_nye','London Ticket Announcement 2026')
            add(c,self.passport,'uk_services','Renew Adult Passport Online')
            add(c,'https://www.gov.uk/register-to-vote','uk_services','Register To Vote')
            add(c,'https://www.nhs.uk/nhs-services/register-gp','nhs_services','How to Register with a GP Surgery')
            add(c,'https://www.nhs.uk/nhs-services/dentist','nhs_services','Find NHS Dentist')
            add(c,'https://developer.mozilla.org/en-US/docs/Web/HTTP','mdn_http','HTTP Documentation')
        with e.dbopen(self.p12) as c:
            fp=r9.digest([dict(x) for x in c.execute('SELECT url,source_id,title,content_sha256,indexed FROM pages ORDER BY url')])
        q=[];ratings=[]
        for i in range(1,16):
            matches=[{'url':self.passport,'position':1}] if i==3 else []
            q.append({'id':f'q{i:02}', 'q': 'How do I renew my adult passport?' if i==3 else f'Research query number {i}', 'results':matches})
            ratings.append({'id':f'q{i:02}','judgements':[{'url':self.passport,'position':1,'grade':3,'answer':'yes'}] if i==3 else []})
        doc={'version':'r2p12', 'index_fingerprint':fp,'questions':q}
        sha=r9.digest(doc);doc['results_sha256']=sha
        self.report=self.root/'query_results.json';self.report.write_text(json.dumps(doc))
        self.review=self.root/'review.json';self.review.write_text(json.dumps({'version':'r2p12-human-review','results_sha256':sha,'questions':ratings}))
        self.patcher=patch.object(p17,'REVIEW_SHA',sha);self.patcher.start();self.addCleanup(self.patcher.stop)

    def run_merge(self):
        return p17.execute(self.p16,self.p12,self.report,self.review,self.root/'combined')

    def test_merge_eight_new_source_pages_except_conflict(self):
        r=self.run_merge()
        self.assertEqual(r['combined_index']['indexed_pages'],9)
        self.assertEqual(r['combined_index']['sources'],4)
        self.assertEqual(r['combined_index']['sitemap_leads_retained'],112)
        self.assertEqual(len(r['new_pages_imported']),5)
        self.assertEqual(len(r['skipped_origin_policy_conflicts']),1)
        self.assertEqual(r['query_count'],19)
        self.assertEqual(r['network_requests'],0)
        self.assertEqual(r['paid_search_provider_calls'],0)
        with p17.ro(self.root/'combined'/'combined_research_index.sqlite') as c:
            self.assertFalse(c.execute("SELECT 1 FROM pages WHERE url LIKE '%press-release'").fetchone())
            self.assertTrue(c.execute('SELECT 1 FROM pages WHERE url=?',(self.passport,)).fetchone())

    def test_owner_db_hashes_unchanged(self):
        h1=p17.p16.sha256(self.p16);h2=p17.p16.sha256(self.p12)
        self.run_merge();self.assertEqual(p17.p16.sha256(self.p16),h1);self.assertEqual(p17.p16.sha256(self.p12),h2)

    def test_provenance_and_preexisting_grades_preserved(self):
        r=self.run_merge()
        q=next(x for x in r['questions'] if x['id']=='q03')
        self.assertEqual(q['results'][0]['url'],self.passport)
        self.assertEqual(q['results'][0]['previous_human_grade'],3)

    def test_reject_tampered_human_review(self):
        d=json.loads(self.review.read_text());d['results_sha256']='bad';self.review.write_text(json.dumps(d))
        with self.assertRaisesRegex(p17.Hold,'fingerprint'):self.run_merge()

    def test_reject_forged_query_results_hash(self):
        d=json.loads(self.report.read_text());d['questions'][0]['q']='tampered';self.report.write_text(json.dumps(d))
        with self.assertRaisesRegex(p17.Hold,'fingerprint'):self.run_merge()

    def test_reject_p12_index_changes(self):
        with e.dbopen(self.p12) as c:c.execute('UPDATE pages SET title=? WHERE url=?',('altered',self.passport))
        with self.assertRaisesRegex(p17.Hold,'live_index_fingerprint'):self.run_merge()

    def test_reject_missing_p16_page(self):
        with e.dbopen(self.p16) as c:e.purge_page(c,p17.CITY+'diwali-square-2026')
        with self.assertRaisesRegex(p17.Hold,'four_page'):self.run_merge()

    def test_reject_missing_p16_candidates(self):
        with e.dbopen(self.p16) as c:c.execute('DELETE FROM sitemap_candidates WHERE rowid IN (SELECT rowid FROM sitemap_candidates LIMIT 1)')
        with self.assertRaisesRegex(p17.Hold,'four_page'):self.run_merge()

    def test_reject_source_rights_escalation(self):
        with e.dbopen(self.p12) as c:c.execute("UPDATE sources SET display_mode='licensed_snippet' WHERE source_id='nhs_services'")
        with self.assertRaisesRegex(p17.Hold,'source_approval'):self.run_merge()

    def test_reject_unapproved_source(self):
        with e.dbopen(self.p12) as c:c.execute("UPDATE sources SET approved=0 WHERE source_id='mdn_http'")
        with self.assertRaisesRegex(p17.Hold,'source_approval'):self.run_merge()

    def test_reject_out_of_scope_page(self):
        with e.dbopen(self.p12) as c:c.execute('UPDATE pages SET url=? WHERE url=?',('https://www.gov.uk/secret/outside',self.passport))
        with self.assertRaisesRegex(p17.Hold,'live_index_fingerprint|outside_source'):self.run_merge()

    def test_refuse_existing_destination(self):
        (self.root/'combined').mkdir()
        with self.assertRaisesRegex(p17.Hold,'already_exists'):self.run_merge()

    def test_reject_same_db_as_both_inputs(self):
        with self.assertRaisesRegex(p17.Hold,'collision'):p17.execute(self.p16,self.p16,self.report,self.review,self.root/'different')

    def test_html_escapes_input(self):
        report={'combined_index':{'sources':1,'indexed_pages':1},'skipped_origin_policy_conflicts':[],
         'questions':[{'query':'<svg onload=alert(1)>','coverage_status':'NO_INDEXED_MATCH','results':[]}]}
        result=p17.render(report)
        self.assertIn('&lt;svg',result)
        self.assertNotIn('<svg onload',result)

    def test_no_network_or_engine_crawl_used(self):
        with patch('pulse_search_engine.crawl',side_effect=AssertionError('no crawling')):
            r=self.run_merge()
        self.assertEqual(r['network_requests'],0)

    def test_different_year_suppressed_in_combined(self):
        r=self.run_merge()
        q=next(x for x in r['questions'] if '2027' in x['query'])
        self.assertEqual(q['coverage_status'],'NO_INDEXED_MATCH')

if __name__=='__main__':unittest.main()
