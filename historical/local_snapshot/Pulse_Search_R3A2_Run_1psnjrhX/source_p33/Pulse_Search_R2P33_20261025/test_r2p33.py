import collections,json,sqlite3,tempfile,unittest
from pathlib import Path
import r2p33_candidate as candidate
import r2p32_candidate as p32
import r2p32_evidence as audit
import r2p33_audit as a33
import pulse_search_r2p31 as p31
HERE=Path(__file__).resolve().parent
ROWS=json.loads((HERE/'metadata_proxy.json').read_text())

class R2P33Tests(unittest.TestCase):
 def test_71_frozen_probe_classifications(self):
  expect=collections.Counter({'EXPECTED_RETRIEVAL_BEHAVIOUR':56,'UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE':15})
  actual=collections.Counter(audit.classify(p,candidate.rank(p[1],ROWS)[0]) for p in audit.PROBES+audit.HELDOUT)
  self.assertEqual(actual,expect)
 def test_previous_sealed_heldout_six_recovered(self):
  fixed=[p for p in audit.HELDOUT if audit.classify(p,p32.rank(p[1],ROWS)[0])=='POTENTIAL_RETRIEVAL_ERROR']
  self.assertEqual(len(fixed),6)
  self.assertTrue(all(audit.classify(p,candidate.rank(p[1],ROWS)[0])=='EXPECTED_RETRIEVAL_BEHAVIOUR' for p in fixed))
 def test_fresh_untouched_18_reports_four_misses(self):
  cnt=collections.Counter(audit.classify(p,candidate.rank(p[1],ROWS)[0]) for p in a33.NEW_HOLDOUT)
  self.assertEqual(cnt,collections.Counter({'EXPECTED_RETRIEVAL_BEHAVIOUR':10,'POTENTIAL_RETRIEVAL_ERROR':4,'UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE':4}))
 def test_prior_36_retrieval_first_preserved_except_exact_series(self):
  r=json.loads((HERE/'owner_R2P31_report.json').read_text())
  changes=[]
  for q in r['questions']:
   got,_,_=candidate.rank(q['query'],ROWS)
   orig=q['results'][0]['url'] if q['results'] else None
   cur=got[0]['url'] if got else None
   if orig!=cur:changes.append((q['query'],got[0]['title'] if got else None))
  self.assertEqual(changes,[('What happened during London Open House over the years?','London Open House 2025 | London City Hall')])
 def test_no_query_to_url_mapping(self):
  import inspect
  s=inspect.getsource(candidate)
  self.assertNotIn('www.gov.uk/',s)
  self.assertNotIn('london.gov.uk/events/',s)
 def test_lost_passport_is_page_retrieval_not_fact(self):
  q='Guide for replacing a lost UK adult passport'
  got,st,sp=candidate.rank(q,ROWS)
  self.assertTrue(got and 'passport' in got[0]['title'].lower())
  self.assertEqual(st,'MATCHES_UNVERIFIED')
 def test_trafalgar_is_not_venue_verified(self):
  got,_,sp=candidate.rank('Eid celebration at Trafalgar Square 2026',ROWS)
  self.assertTrue(got)
  self.assertIn('unverified_detail',sp)
 def test_government_catalog(self):
  got,_,sp=candidate.rank('Government service applications on GOV.UK',ROWS)
  self.assertGreaterEqual(len(got),2)
  self.assertTrue(all('www.gov.uk' in x['url'] for x in got))
 def test_exclusions_and_contradictory_geography(self):
  for q,prohibit in [('London festivals 2026 excluding St Patrick\'s','st-patricks-festival-2026'),('London events 2027 but not Eid','/events/eid')]:
   got,_,_=candidate.rank(q,ROWS)
   self.assertTrue(got)
   self.assertTrue(all(not x['url'].endswith(prohibit) for x in got))
  self.assertFalse(candidate.rank('London events 2027 only in Edinburgh',ROWS)[0])
 def test_live_and_price_claims_are_not_corroborated(self):
  for q in ['London events 2027 that have sold out','Which 2027 London events have free entry confirmed?', 'Will it rain in Newbury tomorrow?']:
   self.assertFalse(candidate.rank(q,ROWS)[0])
 def test_production_is_not_authorized(self):
  self.assertEqual(a33.VERSION,'R2-P33-ThreeWayShadow-v1')
 def test_frozen_evidence_identity(self):
  self.assertEqual(a33.sha(HERE/'owner_R2P32_report.json'),a33.PREVIOUS_AUDIT_SHA)
  self.assertEqual(a33.sha(HERE/'owner_R2P31_report.json'),audit.PRIOR_SHA)
 def test_sqlite_read_only(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.db'
   with sqlite3.connect(p) as conn:conn.execute('CREATE TABLE t(x INT)')
   with audit.open_ro(p) as conn:
    self.assertEqual(conn.execute('PRAGMA query_only').fetchone()[0],1)
    with self.assertRaises(sqlite3.DatabaseError):conn.execute('INSERT INTO t VALUES (1)')
 def test_no_raw_body_in_page_signals(self):
  with sqlite3.connect(':memory:') as c:
   c.row_factory=sqlite3.Row
   c.executescript('CREATE TABLE sources(source_id TEXT,approved INT,enabled INT,display_mode TEXT); CREATE TABLE pages(url TEXT,title TEXT,body TEXT,fetched_at TEXT,source_id TEXT,indexed INT);')
   c.execute("INSERT INTO sources VALUES ('s',1,1,'metadata_only')")
   c.execute("INSERT INTO pages VALUES ('https://x.org/foo','GP surgery','PUBLISHER BODY PRIVATE GP','2026-10-25','s',1)")
   signal=audit.page_signals(c,[{'url':'https://x.org/foo','title':'GP surgery'}],{'terms':['gp']})
   self.assertFalse(signal[0]['publisher_body_exported']);self.assertNotIn('PUBLISHER BODY',json.dumps(signal))
 def test_owner_index_pinned(self):
  self.assertEqual(a33.OWNER_SHA,'bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d')

if __name__=='__main__':unittest.main()
