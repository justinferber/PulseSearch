import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import pulse_search_p19 as p
import pulse_search_engine as eng
import pulse_search_p11 as shadow

class IntentTests(unittest.TestCase):
    def test_weather_now(self):self.assertEqual(p.live_capability_needed('Is it raining in Glasgow right now?'),'current_weather')
    def test_weather_today(self):self.assertEqual(p.live_capability_needed('What is the weather in Berlin today?'),'current_weather')
    def test_weather_no_live_time(self):self.assertIsNone(p.live_capability_needed('What does a weather forecast mean?'))
    def test_weather_historical(self):self.assertIsNone(p.live_capability_needed('What was the weather in London in 1910?'))
    def test_pharmacies_now(self):self.assertEqual(p.live_capability_needed('Which pharmacies in Bristol are open now?'),'live_business_hours')
    def test_restaurants_near_me(self):self.assertEqual(p.live_capability_needed('Which restaurants near me are open now?'),'live_business_hours')
    def test_open_historical(self):self.assertIsNone(p.live_capability_needed('How do I open a restaurant business?'))
    def test_online_buying_guide(self):self.assertIsNone(p.live_capability_needed('How do I buy a passport renewal online?'))
    def test_inventory_stock(self):self.assertEqual(p.live_capability_needed('Are vegan hiking boots in stock near Manchester today?'),'live_retail_inventory')
    def test_manchester_shopping(self):self.assertEqual(p.live_capability_needed('Where can I buy vegan boots in Manchester today?'),'live_retail_inventory')
    def test_london_events_unblocked(self):self.assertIsNone(p.live_capability_needed("What events are happening in London for New Year's Eve 2026?"))
    def test_ticket_schedule_unblocked(self):self.assertIsNone(p.live_capability_needed('When do London fireworks tickets go on sale?'))
    def test_gov_guide_unblocked(self):self.assertIsNone(p.live_capability_needed('How do I renew my adult passport?'))
    def test_blank_or_malicious_query(self):
        for q in ('','x'*300,None):
            with self.assertRaises(p.Hold):p.live_capability_needed(q)
    def test_remove_unverified_live_hit(self):
        fake=[{'url':'https://www.gov.uk/register-to-vote'}]
        out=p.guard_static_index('Where can I buy vegan boots in Manchester today?',fake)
        self.assertEqual(out['results'],[])
        self.assertEqual(out['suppressed_unverified_hits'],1)
        self.assertEqual(out['status'],'LIVE_DATA_REQUIRED_NOT_VERIFIED_IN_STATIC_INDEX')
    def test_preserve_event_hit(self):
        fake=[{'url':'https://www.london.gov.uk/events/foo'}]
        out=p.guard_static_index('London Games Festival 2026',fake)
        self.assertEqual(out['results'],fake)
    def test_no_match_not_absence_from_web(self):
        out=p.guard_static_index('Impossible static index query here',[])
        self.assertEqual(out['status'],'NO_INDEXED_MATCH')
    def test_novel_set_distinct(self):
        self.assertEqual(len(p.NOVEL_QUERIES),12)
        self.assertEqual(len(set(q.casefold() for q in p.NOVEL_QUERIES)),12)

class SyntheticFixtureTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        self.root=Path(td.name);self.db=self.root/'index.sqlite'
        eng.initdb(self.db)
        with eng.dbopen(self.db) as c:
            eng.register_sources(c,[{'source_id':'gov','origin':'https://www.gov.uk',
              'allowed_paths':['/register-to-vote'],'collection_approved':True,
              'display_mode':'metadata_only','rights_basis':'Internal research only; no commercial publication rights.'}])
            src=c.execute('SELECT * FROM sources WHERE source_id=?',('gov',)).fetchone()
            title='Register to vote in the UK';body='Learn to register to vote at GOV UK'
            digest=hashlib.sha256((title+'\n'+body).encode()).hexdigest()
            eng.index_page(c,'https://www.gov.uk/register-to-vote',src,title,body,digest,True)
        self.q=[];self.j=[]
        for i in range(1,20):
            qid=f'q{i:02}' if i<=15 else f'additional_{i-15}'
            if i==15:query='Where can I buy vegan boots in Manchester today?'
            elif i==9:query='Which restaurants near me are open now?'
            elif i==14:query='What is the weather in Berlin right now?'
            else:query='How do I register to vote?' if i<=13 else 'London Games Festival 2026'
            # one false positive (q15), 13 direct + 2 partial, 3 no match
            if i in (9,14,19):grade=None
            elif i==15:grade=0
            elif i in (1,11):grade=2
            else:grade=3
            hits= [] if grade is None else [{'url':'https://www.gov.uk/register-to-vote','title':'Register to vote in the UK','source_id':'gov','position':1}]
            self.q.append({'id':qid,'query':query,'results':hits})
            self.j.append({'id':qid,'judgements':[] if grade is None else [{'url':'https://www.gov.uk/register-to-vote','position':1,'grade':grade,'answer':p.SCORE[grade]}]})

    def test_baseline_counts_fixture(self):
        from collections import Counter
        self.assertEqual(Counter(j['judgements'][0]['grade'] if j['judgements'] else None for j in self.j),{3:13,2:2,0:1,None:3})

    def test_offline_scoring_and_novel_uncertainty(self):
        with patch.object(p,'load_bound',return_value=({'questions':self.q},{'questions':self.j})):
            report=p.create_report('none',self.db,'none')
        self.assertEqual(report['candidate'],{'0':0,'1':0,'2':2,'3':13,'no_match':4})
        self.assertEqual(report['prior'],{'0':1,'1':0,'2':2,'3':13,'no_match':3})
        self.assertEqual(len(report['unseen_queries']),12)
        self.assertTrue(all(q['previously_unjudged'] for q in report['unseen_queries']))
        self.assertEqual(report['paid_search_api_calls'],0)
        self.assertEqual(report['network_requests'],0)
        self.assertEqual(report['database_writes'],0)

    def test_old_human_grade_loss_fails(self):
        self.j[2]['judgements'][0]['grade']=0
        with patch.object(p,'load_bound',return_value=({'questions':self.q},{'questions':self.j})):
            with self.assertRaisesRegex(p.Hold,'human_metrics_changed'):p.create_report('none',self.db,'none')

    def test_lookups_never_write_to_sqlite(self):
        before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        p.row_results(self.db,'How do I register to vote?')
        self.assertEqual(before,hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_html_escaping_and_ungraded(self):
        s=p.render({'unseen_queries':[{'query':'<svg onload=alert(1)>',
          'status':'MATCHES_FOUND_NOT_VERIFIED_ANSWERS','required_capability':None,'results':[
          {'url':'https://www.gov.uk/register-to-vote','title':'<script>bad</script>'}]}]})
        self.assertIn('&lt;svg',s);self.assertNotIn('<svg onload',s)
        self.assertIn('NOT GRADED',s)

    def test_offline_only_even_during_novel_queries(self):
        with patch('pulse_search_engine.crawl',side_effect=AssertionError('network forbidden')):
            with patch.object(p,'load_bound',return_value=({'questions':self.q},{'questions':self.j})):
                p.create_report('none',self.db,'none')

if __name__=='__main__':unittest.main()
