import copy
import json
from pathlib import Path
import tempfile
import unittest

import pulse_search_p12 as p
import pulse_search_engine as e

class PlanTests(unittest.TestCase):
 def setUp(self):
  self.sources,self.seeds,self.questions=p.validate_plan()
 def test_plan(self):
  self.assertEqual((len(self.sources),len(self.seeds),len(self.questions)),(7,11,15))
 def test_no_paid_external_search(self):
  self.assertEqual(p.VERSION,'r2p12-standalone-coverage-pilot')
 def test_unreviewed_origin(self):
  a=copy.deepcopy(self.sources);a[0]['origin']='https://example.com'
  with self.assertRaises(p.PilotHold):p.validate_plan(a,self.seeds,self.questions)
 def test_unreviewed_seed(self):
  a=self.seeds[:];a[0]='https://www.gov.uk/unapproved'
  with self.assertRaises(p.PilotHold):p.validate_plan(self.sources,a,self.questions)
 def test_metadata_only(self):
  a=copy.deepcopy(self.sources);a[0]['display_mode']='licensed_snippet'
  with self.assertRaises((p.PilotHold,e.Hold)):p.validate_plan(a,self.seeds,self.questions)
 def test_negative_questions_present(self):
  self.assertEqual([q['id'] for q in self.questions if q['cohort']=='negative'],['q09','q14','q15'])
 def test_no_user_judgements_preseeded(self):
  self.assertTrue(all('grade' not in q for q in self.questions))
 def test_no_query_change(self):
  a=copy.deepcopy(self.questions);a.pop()
  with self.assertRaises(p.PilotHold):p.validate_plan(self.sources,self.seeds,a)
 def test_seed_cannot_leave_review_scope(self):
  a=self.seeds[:];a[1]='http://127.0.0.1/secret'
  with self.assertRaises(p.PilotHold):p.validate_plan(self.sources,a,self.questions)
 def test_html_query_repeated(self):
  report={'results_sha256':'abc','questions':[{'id':'q01','q':'London New Years Eve 2026','expected_answer':'events listings',
       'results':[{'url':'https://example.com/a','title':'An event','position':1,'source_id':'a'}]}]}
  h=p.review_template(report)
  self.assertGreaterEqual(h.count('London New Years Eve 2026'),2)
  self.assertIn('Save reviewed results JSON',h)
 def test_html_escape(self):
  report={'results_sha256':'a','questions':[{'id':'q01','q':'<script>','expected_answer':'x',
       'results':[{'url':'https://example.com/a','title':'<b>','position':1,'source_id':'a'}]}]}
  h=p.review_template(report)
  self.assertIn('&lt;script&gt;',h)
  self.assertIn('&lt;b&gt;',h)
  self.assertNotIn('<b>',h)
 def test_review_validation_and_scoring(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'index.sqlite';e.initdb(path)
   obj={'version':p.VERSION,'questions':[{'id':'q01','q':'Why is this a test','cohort':'heldout',
       'results':[{'url':'https://www.gov.uk/a','position':1,'title':'A'}]}]}
   obj['index_fingerprint']=p.r9.page_fingerprint(path)
   obj['results_sha256']=p.r9.digest({k:v for k,v in obj.items() if k!='results_sha256'})
   ca=Path(d)/'c.json';ca.write_text(p.dump(obj))
   review={'version':'r2p12-human-review','results_sha256':obj['results_sha256'],
     'questions':[{'id':'q01','judgements':[{'url':'https://www.gov.uk/a','position':1,'grade':3,'answer':'yes'}]}]}
   re=Path(d)/'r.json';re.write_text(p.dump(review))
   scored=p.score(ca,re,path)
   self.assertEqual(scored['top1_direct_answers'],1)
   review['questions'][0]['judgements'][0].update(grade=0,answer='yes');re.write_text(p.dump(review))
   with self.assertRaises(p.PilotHold):p.score(ca,re,path)
   review['questions'][0]['judgements'][0].update(grade=3,answer='yes',url='https://evil.example/');re.write_text(p.dump(review))
   with self.assertRaises(p.PilotHold):p.score(ca,re,path)
 def test_index_mutation_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'index.sqlite';e.initdb(path)
   obj={'version':p.VERSION,'questions':[{'id':'q01','q':'X','cohort':'heldout','results':[]}]}
   obj['index_fingerprint']=p.r9.page_fingerprint(path)
   obj['results_sha256']=p.r9.digest({k:v for k,v in obj.items() if k!='results_sha256'})
   ca=Path(d)/'c.json';ca.write_text(p.dump(obj))
   re=Path(d)/'r.json';re.write_text(p.dump({'version':'r2p12-human-review','results_sha256':obj['results_sha256'],'questions':[{'id':'q01','judgements':[]}]}))
   scored=p.score(ca,re,path)
   self.assertEqual(scored['no_indexed_match'],1)
   with e.dbopen(path) as conn:
    conn.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?)",('test','https://example.com','["/"]',1,'metadata_only','Test only source with explicit fixture approval',1))
    conn.execute("INSERT INTO pages(url,source_id,title,body,content_sha256,fetched_at,indexed) VALUES(?,?,?,?,?,?,?)",('https://example.com/', 'test','Fixture','Text','hash','now',1))
   with self.assertRaises(p.PilotHold):p.score(ca,re,path)

if __name__=='__main__':unittest.main()

class ApiIntegrationTests(unittest.TestCase):
 def test_actual_index_shadow_search_and_no_indexed_match(self):
  with tempfile.TemporaryDirectory() as d:
   db=Path(d)/'p12.sqlite'; e.initdb(db)
   with e.dbopen(db) as c:
    c.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',('gov','https://www.gov.uk','["/register-to-vote"]',1,'metadata_only','Open government research metadata rights review for test only',1))
    cur=c.execute('INSERT INTO pages(url,source_id,title,body,content_sha256,fetched_at,indexed) VALUES(?,?,?,?,?,?,?)',('https://www.gov.uk/register-to-vote','gov','Register to vote online','Register to vote online in the UK. Electoral register instructions.', 'fixture-hash','now',1))
    c.execute('INSERT INTO page_fts(rowid,title,body) VALUES(?,?,?)',(cur.lastrowid,'Register to vote online','Register to vote online in the UK. Electoral register instructions.'))
   self.assertEqual(p.quality(db)['indexed_pages'],1)
   questions=[{'id':'q10','q':'How do I register to vote online in Britain?','expected_answer':'Government voter registration','cohort':'heldout'},
              {'id':'q15','q':'Where can I buy vegan boots in Manchester today?','expected_answer':'Real-time shopping','cohort':'negative'}]
   report=p.build_report(db,questions)
   self.assertEqual(len(report['questions']),2)
   self.assertEqual(report['questions'][0]['results'][0]['source_id'],'gov')
   self.assertEqual(report['questions'][1]['coverage_status'],'NO_INDEXED_MATCH')
   self.assertNotIn('snippet',report['questions'][0]['results'][0])
 def test_new_crawl_refuses_output_directory_already_present(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(p.PilotHold):p.run(d)
