"""No network, no model weights; verify deterministic safety and evaluation rules."""
import json,math,tempfile,unittest
from pathlib import Path
from provision import EXPECTED_REV_PREFIX, WEIGHTS_SHA, WEIGHTS_SIZE, FILES, REQUIREMENTS
from semantic_ranker import DenseConstrainedIndex
from r3a2_extra_cases import CASES
from r3a2_eval import eval_one, verify_owner_report, DB_SHA

class DeterministicFake:
 def encode(self,docs):
  # Fake vectors for testing safety gates only. Never asserted to be semantic.
  return [[1.0]+[0.0]*383 for _ in docs]

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=[{'url':'https://www.london.gov.uk/events/eid-square-2027','title':'Eid on the Square 2027'},
    {'url':'https://www.london.gov.uk/events/diwali-square-2027','title':'Diwali on the Square 2027'},
    {'url':'https://www.london.gov.uk/events/st-patricks-festival-2026','title':"St Patrick's Festival 2026"},
    {'url':'https://www.london.gov.uk/events/london-games-festival-2026','title':'London Games Festival 2026'},
    {'url':'https://www.gov.uk/register-to-vote','title':'Register to vote - GOV.UK'}]
  cls.rank=DenseConstrainedIndex(cls.data,DeterministicFake())
 def test_gated_year(self):
  r=self.rank.search('London festivals 2026')['results']
  self.assertTrue(r);self.assertTrue(all('2026' in x['title'] for x in r))
 def test_geography_conflict(self):self.assertEqual(self.rank.search('London events 2027 only in Edinburgh')['results'],[])
 def test_geo_dont_return_london_for_paris(self):self.assertEqual(self.rank.search('Festivals in Paris in 2027')['results'],[])
 def test_year2038(self):self.assertEqual(self.rank.search('Eid on the Square 2038')['results'],[])
 def test_exclusion_does_not_leak(self):
  rs=self.rank.search('London events 2027 excluding Eid')['results']
  self.assertTrue(rs);self.assertTrue(all('Eid' not in x['title'] for x in rs))
 def test_other_exclusion(self):
  rs=self.rank.search("London festivals 2026 excluding St Patrick's Festival")['results']
  self.assertTrue(rs);self.assertTrue(all('Patrick' not in x['title'] for x in rs))
 def test_dynamic_abstention(self):self.assertEqual(self.rank.search('Will it snow in Bristol tomorrow?')['results'],[])
 def test_facts_are_not_claims(self):
  r=self.rank.search('What is the fee for passport renewal?')
  self.assertFalse(any('verified_factual_answer' in x for x in r['results']))
 def test_no_urls_embedded_in_model(self):
  import inspect,semantic_ranker
  self.assertNotIn('gov.uk/register-to-vote',inspect.getsource(semantic_ranker))
 def test_expected_published_weight(self):
  self.assertEqual(WEIGHTS_SHA,'3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad')
  self.assertEqual(WEIGHTS_SIZE,133466304)
 def test_no_pickle_bin(self):self.assertTrue('pytorch_model.bin' not in FILES)
 def test_model_revision_gate(self):self.assertEqual(EXPECTED_REV_PREFIX,'5c38ec7')
 def test_dependencies_explicit_top_level(self):
  self.assertTrue(all('==' in x for x in REQUIREMENTS));self.assertIn('torch==2.6.0+cpu',REQUIREMENTS)
 def test_frozen_extra_cases(self):self.assertEqual(len(CASES),24)
 def test_report_refuses_wrong_benchmark(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'report.json';f.write_text(json.dumps({'status':'garbage','case_count':30,'failures':8}))
   with self.assertRaises(ValueError):verify_owner_report(f)
 def test_eval_negative_stays_empty(self):
  x=eval_one('Newbury weather tomorrow','no_result','',self.rank)
  self.assertEqual(x['verdict'],'PASS_SAFETY')
 def test_no_calibration_claim(self):
  x=self.rank.search('Where can I register to vote?')['results']
  self.assertTrue(all(y['confidence']=='NOT_CALIBRATED_METADATA_RELEVANCE_ONLY' for y in x))
if __name__=='__main__':unittest.main()
