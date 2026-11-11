import collections,inspect,json,sqlite3,tempfile,unittest
from pathlib import Path
import r2p34_candidate as p34
import r2p33_candidate as p33
import r2p32_evidence as base
import r2p33_audit as prev
import r2p34_audit as audit
ROOT=Path(__file__).resolve().parent
ROWS=json.loads((ROOT/'metadata_proxy.json').read_text(encoding='utf8'))

class R2P34Tests(unittest.TestCase):
 def test_frozen_71_zero_retrieval_regressions(self):
  a=collections.Counter(base.classify(x,p34.rank(x[1],ROWS)[0]) for x in base.PROBES+base.HELDOUT)
  self.assertEqual(a,{'EXPECTED_RETRIEVAL_BEHAVIOUR':56,'UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE':15})
 def test_existing_18_holdout_repaired(self):
  a=collections.Counter(base.classify(x,p34.rank(x[1],ROWS)[0]) for x in prev.NEW_HOLDOUT)
  self.assertEqual(a,{'EXPECTED_RETRIEVAL_BEHAVIOUR':14,'UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE':4})
 def test_new_sealed_20_discloses_failures(self):
  a=collections.Counter(base.classify(x,p34.rank(x[1],ROWS)[0]) for x in audit.NEW_SEALED_HOLDOUT)
  self.assertEqual(a,{'EXPECTED_RETRIEVAL_BEHAVIOUR':9,'POTENTIAL_RETRIEVAL_ERROR':7,'UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE':4})
 def test_four_previous_holdout_fixes(self):
  miss=[x for x in prev.NEW_HOLDOUT if base.classify(x,p33.rank(x[1],ROWS)[0])=='POTENTIAL_RETRIEVAL_ERROR']
  self.assertEqual(len(miss),4)
  self.assertTrue(all(base.classify(x,p34.rank(x[1],ROWS)[0])=='EXPECTED_RETRIEVAL_BEHAVIOUR' for x in miss))
 def test_preserve_36_known_firsts_except_series(self):
  old=json.loads((ROOT/'owner_R2P31_report.json').read_text())
  changes=[]
  for x in old['questions']:
   results=p34.rank(x['query'],ROWS)[0]
   first=x['results'][0]['url'] if x['results'] else None
   after=results[0]['url'] if results else None
   if after!=first:changes.append((x['query'],results[0]['title'] if results else None))
  self.assertEqual(changes,[('What happened during London Open House over the years?','London Open House 2025 | London City Hall')])
 def test_avoid_lookalike_named_series(self):
  q='What were the London Open House editions?'
  results,status,spec=p34.rank(q,ROWS)
  self.assertGreaterEqual(len(results),3)
  self.assertTrue(all(r['title'].startswith('London Open House') for r in results))
  self.assertEqual(spec.get('series_identity_filter'),'CONTIGUOUS_QUERY_NAME_IN_TITLE')
 def test_series_paraphrases_are_generic(self):
  queries=['Historical editions of London Open House','Tell me about past Eid on the Square editions']
  for q in queries:
   results,status,spec=p34.rank(q,ROWS)
   self.assertGreaterEqual(len(results),2,q)
   self.assertEqual(spec.get('kind'),'series')
 def test_respects_negative_and_dynamic(self):
  for q in ['London events 2027 apart from Eid','London events 2027 but not Eid']:
   got,_,_=p34.rank(q,ROWS)
   self.assertGreater(len(got),0)
   self.assertTrue(all(not x['url'].endswith('/events/eid') for x in got))
  for q in ['Will it rain in Newbury tomorrow?','Diwali on the Square 2031','London events 2027 only in Edinburgh','London events 2027 that have sold out']:
   self.assertFalse(p34.rank(q,ROWS)[0],q)
 def test_no_query_to_url_lookup(self):
  src=inspect.getsource(p34)
  self.assertNotIn('london.gov.uk/events/',src)
  self.assertNotIn('gov.uk/',src)
  self.assertNotIn('https://',src)
 def test_original_provenance_reports(self):
  self.assertEqual(base.shaf(ROOT/'owner_R2P31_report.json'),base.PRIOR_SHA)
  self.assertEqual(base.shaf(ROOT/'owner_R2P32_report.json'),prev.PREVIOUS_AUDIT_SHA)
 def test_owner_digest_and_new_probe_count(self):
  self.assertEqual(audit.OWNER_SHA,'bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d')
  self.assertEqual(len(audit.NEW_SEALED_HOLDOUT),20)
 def test_sqlite_protected_read(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.db'
   with sqlite3.connect(p) as db:db.execute('CREATE TABLE t(a INT)')
   with base.open_ro(p) as db:
    self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
    with self.assertRaises(sqlite3.DatabaseError):db.execute('INSERT INTO t VALUES(2)')
 def test_factual_not_claimed(self):
  self.assertEqual(sum(x[2]=='fact_unknown' for x in audit.NEW_SEALED_HOLDOUT),4)
  self.assertIn('factual_answers_verified',inspect.getsource(audit))
 def test_no_raw_publisher_export(self):
  with sqlite3.connect(':memory:') as db:
   db.row_factory=sqlite3.Row
   db.executescript('CREATE TABLE sources(source_id TEXT,approved INT,enabled INT,display_mode TEXT); CREATE TABLE pages(url TEXT,title TEXT,body TEXT,fetched_at TEXT,source_id TEXT,indexed INT);')
   db.execute("INSERT INTO sources VALUES ('s',1,1,'metadata_only')")
   db.execute("INSERT INTO pages VALUES ('https://x.invalid/demo','NHS test','PRIVATE BODY PUBLISHER', '2026-10-25','s',1)")
   signal=base.page_signals(db,[{'url':'https://x.invalid/demo','title':'NHS test'}],{'terms':['test']})
   self.assertNotIn('PRIVATE BODY',json.dumps(signal))

if __name__=='__main__':unittest.main()
