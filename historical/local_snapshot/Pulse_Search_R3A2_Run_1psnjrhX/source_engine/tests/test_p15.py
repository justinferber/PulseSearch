import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from pulse_search_p15 import Hold, score_urls, read_candidates, create_report, html_report

class R2P15Tests(unittest.TestCase):
  def setUp(self):
    self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
    self.db=Path(self.temp.name)/'research.db'
    self.c=sqlite3.connect(self.db)
    self.c.executescript('''CREATE TABLE sources(source_id TEXT,origin TEXT,paths TEXT,enabled INT,approved INT,display_mode TEXT,rights_basis TEXT);
      CREATE TABLE sitemap_candidates(source_id TEXT,url TEXT,sitemap_url TEXT,discovered_at TEXT,query_score INT);
      CREATE TABLE pages(indexed INT);
      INSERT INTO sources VALUES('london','https://www.london.gov.uk','["/events/"]',1,1,'metadata_only','Internal-only source review.');''')
    for slug in ('london-new-years-eve-2026','london-games-festival-2026','diwali-square-2026','london-new-years-eve-2025','city-hall-open-house-2026'):
      self.c.execute('INSERT INTO sitemap_candidates VALUES(?,?,?,?,?)',('london','https://www.london.gov.uk/events/'+slug,'https://www.london.gov.uk/sitemap.xml','2026-10-23',3))
    self.c.commit();self.c.close()
  def test_existing_source_read(self):
    rows,src=read_candidates(self.db,'london');self.assertEqual(len(rows),5)
    self.assertEqual(src['display_mode'],'metadata_only')
  def test_no_search_provider(self):
    r=create_report(self.db,'london',['London Games Festival 2026'])
    self.assertEqual(r['paid_search_calls'],0);self.assertEqual(r['external_network_calls'],0)
    self.assertEqual(r['index_writes'],0)
  def test_query_time_ranking(self):
    r=create_report(self.db,'london',["London New Year's Eve 2026"])
    self.assertTrue(r['questions'][0]['matches'][0]['url'].endswith('london-new-years-eve-2026'))
  def test_other_independent_query(self):
    r=create_report(self.db,'london',['London Games Festival 2026'])
    self.assertTrue(r['questions'][0]['matches'][0]['url'].endswith('london-games-festival-2026'))
  def test_explicit_year_mismatch(self):
    r=create_report(self.db,'london',["London New Year's Eve 2027"])
    self.assertFalse(any('2026' in x['url'] for x in r['questions'][0]['matches']))
  def test_irrelevant_query_abstains(self):
    r=create_report(self.db,'london',['UK adult passport online renewal'])
    self.assertEqual(r['questions'][0]['matches'],[])
  def test_no_db_modify(self):
    orig=self.db.read_bytes()
    create_report(self.db,'london',['London Games Festival 2026'])
    self.assertEqual(self.db.read_bytes(),orig)
  def test_bad_db_hold(self):
    with self.assertRaises(Hold):read_candidates(self.db,'wrong')
  def test_out_of_scope_guard(self):
    with sqlite3.connect(self.db) as c:
      c.execute('INSERT INTO sitemap_candidates VALUES(?,?,?,?,?)',('london','https://evil.org/events/private','x','2026',0))
    with self.assertRaisesRegex(Hold,'out_of_scope'):read_candidates(self.db,'london')
  def test_out_of_scope_path_guard(self):
    with sqlite3.connect(self.db) as c:
      c.execute('INSERT INTO sitemap_candidates VALUES(?,?,?,?,?)',('london','https://www.london.gov.uk/private','x','2026',0))
    with self.assertRaisesRegex(Hold,'out_of_scope'):read_candidates(self.db,'london')
  def test_disable_source(self):
    with sqlite3.connect(self.db) as c:c.execute("UPDATE sources SET enabled=0 WHERE source_id='london'")
    with self.assertRaisesRegex(Hold,'disabled'):read_candidates(self.db,'london')
  def test_duplicate_queries_hold(self):
    with self.assertRaises(Hold):create_report(self.db,'london',['A','A'])
  def test_bad_result_limit(self):
    with self.assertRaises(Hold):score_urls([], 'query', 20)
  def test_candidate_not_verified(self):
    r=create_report(self.db,'london',['Diwali London 2026'])
    self.assertTrue(all(x['status']=='UNVERIFIED_URL_CANDIDATE' for x in r['questions'][0]['matches']))
  def test_html_escapes(self):
    r=create_report(self.db,'london',['London <script>alert(1)</script>'])
    s=html_report(r)
    self.assertIn('&lt;script&gt;',s)
    self.assertNotIn('<script>',s)
  def test_no_match_not_internet_absence(self):
    r=create_report(self.db,'london',['unrelated supermarket discounts'])
    self.assertIn('not proof the internet',html_report(r))
  def test_source_constrains_catalog(self):
    r=create_report(self.db,'london',['London events 2026'])
    self.assertEqual(r['source']['approved_scope_paths'],['/events/'])
  def test_max_queries(self):
    with self.assertRaisesRegex(Hold,'bad_questions'):create_report(self.db,'london',['query']*21)

if __name__=='__main__':unittest.main()
