import collections,json,sqlite3,sys,tempfile,unittest
from pathlib import Path

import r2p32_candidate as cand
import r2p32_evidence as audit
import pulse_search_r2p31 as p31

HERE=Path(__file__).resolve().parent
PROXY=json.loads((HERE/'metadata_proxy.json').read_text())

class R2P32Tests(unittest.TestCase):
 def test_probe_manifest_unique(self):
  self.assertEqual(len(audit.PROBES),55)
  self.assertEqual(len(audit.HELDOUT),16)
  self.assertEqual(len(set(v[1] for v in audit.PROBES+audit.HELDOUT)),71)
 def test_frozen_55_development_behaviours(self):
  stats=collections.Counter()
  for p in audit.PROBES:
   with self.subTest(question=p[1]):
    res,_,_=cand.rank(p[1],PROXY)
    status=audit.classify(p,res)
    self.assertNotEqual(status,'POTENTIAL_RETRIEVAL_ERROR')
    stats[status]+=1
  self.assertEqual(stats['EXPECTED_RETRIEVAL_BEHAVIOUR'],44)
  self.assertEqual(stats['UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE'],11)
 def test_16_heldout_is_reported_not_fixed(self):
  # A known six-recall-miss holdout is sealed, not an acceptance promise.
  stats=collections.Counter(audit.classify(p,cand.rank(p[1],PROXY)[0]) for p in audit.HELDOUT)
  self.assertEqual(stats['POTENTIAL_RETRIEVAL_ERROR'],6)
  self.assertEqual(stats['EXPECTED_RETRIEVAL_BEHAVIOUR'],6)
  self.assertEqual(stats['UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE'],4)
 def test_exclusion_policy(self):
  for q,url in [("London events 2027 excluding Eid",'/events/eid'),
                ("London festivals 2026 but not St Patrick's",'/events/st-patricks-festival-2026')]:
   with self.subTest(q=q):
    results,_,_=cand.rank(q,PROXY)
    self.assertTrue(results)
    self.assertTrue(all(not x['url'].endswith(url) for x in results))
 def test_geo_conflict(self):
  res,status,_=cand.rank('London events 2027 only in Edinburgh',PROXY)
  self.assertEqual(res,[])
  self.assertEqual(status,'WITHHELD_CONTRADICTORY_GEOGRAPHY')
 def test_factual_claims_conservative(self):
  for q in ['London events 2027 that have sold out','Which London 2026 festivals were cancelled?',
            'Which 2027 London events have confirmed free entry?']:
   with self.subTest(q=q):self.assertEqual(cand.rank(q,PROXY)[0],[])
 def test_year_guards(self):
  for q in ['Armed Forces Day 2044','Diwali on the Square 2038']:
   self.assertFalse(cand.rank(q,PROXY)[0])
 def test_prior_36_no_withheld_regressions(self):
  src=json.loads((HERE/'owner_R2P31_report.json').read_text())
  for p in src['questions']:
   with self.subTest(q=p['query']):
    res,_,_=cand.rank(p['query'],PROXY)
    if not p['results']:self.assertFalse(res)
    elif p['kind']!='series':self.assertEqual(res[0]['url'],p['results'][0]['url'])
 def test_source_series_prefer_exact_name(self):
  res,_,_=cand.rank('What happened during London Open House over the years?',PROXY)
  self.assertTrue(res)
  self.assertTrue(res[0]['title'].startswith('London Open House'))
 def test_no_commercial_body_export(self):
  c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
  c.executescript('''CREATE TABLE sources(source_id TEXT,approved INTEGER,enabled INTEGER,display_mode TEXT);
  CREATE TABLE pages(url TEXT,title TEXT,body TEXT,fetched_at TEXT,source_id TEXT,indexed INTEGER);''')
  c.execute("INSERT INTO sources VALUES ('s',1,1,'metadata_only')")
  c.execute("INSERT INTO pages VALUES ('https://example.com/test','What is HTTP','SENSITIVE PUBLISHER PROSE HTTP','2026-10-25','s',1)")
  out=audit.page_signals(c,[{'url':'https://example.com/test','title':'What is HTTP'}],{'terms':['http']})
  self.assertEqual(out[0]['indexed_body_anchor_hits'],1)
  self.assertNotIn('body',out[0])
  self.assertNotIn('SENSITIVE',json.dumps(out))
  self.assertFalse(out[0]['publisher_body_exported'])
  c.close()
 def test_read_only_uri_and_changes_prohibited(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.db'
   with sqlite3.connect(p) as c:c.execute('CREATE TABLE t(a INT)')
   with audit.open_ro(p) as c:
    self.assertEqual(c.execute('PRAGMA query_only').fetchone()[0],1)
    with self.assertRaises(sqlite3.OperationalError):c.execute('INSERT INTO t VALUES (1)')
 def test_report_hash_source_exact(self):
  self.assertEqual(audit.shaf(HERE/'owner_R2P31_report.json'),audit.PRIOR_SHA)
  self.assertEqual(audit.VERSION,'R2-P32-Evidence-And-Adversarial-v1')

if __name__=='__main__':unittest.main()
