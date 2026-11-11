import unittest,sys,sqlite3,tempfile,os,hashlib
from pathlib import Path
from hybrid_core import HybridIndex,parse
from evidence_gate import evidence_signals,ReliabilityCalibrator
from offline_encoder import PinnedLocalEncoder,OfflineEncoderUnavailable
from r2p35_audit import check

class HybridResearchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rows=[
  {'url':'https://www.nhs.uk/gps/register','title':'Register with a GP surgery - NHS','body':'How to register at an NHS GP practice', 'display_mode':'metadata_only'},
  {'url':'https://www.gov.uk/register-to-vote','title':'Register to vote','body':'Electoral voter registration','display_mode':'metadata_only'},
  {'url':'https://www.london.gov.uk/events/eid-square-2027','title':'Eid on the Square 2027 | London City Hall','body':'Eid on the square','display_mode':'metadata_only'},
  {'url':'https://www.london.gov.uk/events/st-patricks-day','title':'St Patricks Festival 2027 | London City Hall','body':'St Patricks celebration festival','display_mode':'metadata_only'},
  {'url':'https://www.london.gov.uk/events/st-patricks-day-2025','title':'St Patricks Festival 2025 | London City Hall','body':'2025 historical festival','display_mode':'metadata_only'},
  {'url':'https://www.gov.uk/apply-driving','title':'Apply for your provisional driving licence','body':'Learner drivers permit process','display_mode':'metadata_only'}]
  cls.i=HybridIndex(cls.rows)
 def test_01_dynamic_abstains(self):self.assertEqual(self.i.search('Will it rain in London tomorrow?')['status'],'WITHHELD_REQUIRES_LIVE_SOURCE')
 def test_02_stock_abstains(self):self.assertEqual(self.i.search('Which laptop is in stock now?')['results'],[])
 def test_03_geography_conflict(self):self.assertEqual(self.i.search('London events 2027 only in Berlin')['results'],[])
 def test_04_wrong_year(self):self.assertEqual(self.i.search('Eid on the Square 2031')['results'],[])
 def test_05_facet(self):
  r=self.i.search('London festivals 2027');self.assertTrue(r['results']);self.assertTrue(all('festival' in x['title'].casefold() for x in r['results']))
 def test_06_exclusion(self):
  r=self.i.search('London events 2027 excluding Eid');self.assertTrue(all('eid' not in x['title'].lower() for x in r['results']))
 def test_07_contradiction(self):self.assertEqual(self.i.search('Eid on the Square 2027 excluding Eid')['results'],[])
 def test_08_facts_no_answer(self):self.assertIn('FACT_UNVERIFIED',self.i.search('How much is the price of Eid on the Square 2027?')['status'])
 def test_09_read_only_signals(self):
  s=evidence_signals('Starts 11:30 tickets £5', 'metadata_only');self.assertEqual(s['signals']['clock_like'],1);self.assertFalse(s['factual_claim_verified'])
 def test_10_no_confidence_probability(self):self.assertIsNone(ReliabilityCalibrator([(0.6,True)]).estimate(.6))
 def test_11_no_local_model_unverified(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(OfflineEncoderUnavailable):PinnedLocalEncoder(td)
 def test_12_lexical(self):self.assertEqual(self.i.search('register with a GP surgery')['results'][0]['title'],'Register with a GP surgery - NHS')
 def test_13_synonym(self):self.assertEqual(self.i.search('How can I enrol as a new patient with a doctor?')['results'][0]['title'],'Register with a GP surgery - NHS')
 def test_14_negation_no_leak(self):self.assertEqual(self.i.search('Eid on the Square 2027 except Eid')['results'],[])
 def test_15_no_writes(self):self.assertFalse(hasattr(self.i,'persist'))
 def test_16_gov_catalog(self):self.assertTrue(all('gov.uk' in x['url'] for x in self.i.search('What government services online can I use?')['results']))
 def test_17_false_planets(self):self.assertEqual(self.i.search('Apply for mortgage on Mars')['results'],[])
 def test_18_calibration_threshold(self):self.assertEqual(ReliabilityCalibrator().status,'INSUFFICIENT_INDEPENDENT_LABELS_NO_PROBABILITIES')
 def test_19_all_legacy_types(self):
  for kind in ('url','withhold','exclude','year_event','year_festival','year_celebration','gov_catalog','series','fact_unknown'):
   self.assertIsInstance(check(('test',kind,'2027'),[]),str)
 def test_20_model_backend_disabled(self):self.assertEqual(self.i.capabilities['dense_model'],'DISABLED_UNLESS_LOCAL_PINNED_BACKEND_PROVIDED')
if __name__=='__main__':unittest.main()
