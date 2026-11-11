import unittest, tempfile
from pathlib import Path
from r3a_eval import check_output, sha, R35_REPORT_SHA, OWNER_SHA
from r3a_cases import CASES
from r3a_local_model import PinnedSentenceEncoder,ModelHold

URL=lambda p,t='Some name':{'title':t,'url':'https://www.london.gov.uk'+p}

class GateTests(unittest.TestCase):
 def test_case_ids_unique(self):
  self.assertEqual(len(set(x[0] for x in CASES)),len(CASES))
 def test_two_year_edition_requires_both(self):
  exp='/events/london-open-house-2024|/events/london-open-house-2025'
  self.assertEqual(check_output('all',exp,[URL('/events/london-open-house-2025')])[0],'FAIL_MISSING_EDITION')
  self.assertEqual(check_output('all',exp,[URL('/events/london-open-house-2025'),URL('/events/london-open-house-2024')])[0],'PASS_RETRIEVAL')
 def test_exclusion_cannot_pass_empty(self):
  self.assertEqual(check_output('exclude_nonempty','/events/eid',[])[0],'FAIL_EMPTY_DISCOVERY')
 def test_exclusion_fails_forbidden_anywhere(self):
  self.assertEqual(check_output('exclude_nonempty','/events/eid',[URL('/events/black-square-2027'),URL('/events/eid')])[0],'FAIL_EXCLUSION_LEAK')
 def test_exclusion_with_alternatives(self):
  self.assertEqual(check_output('exclude_nonempty','/events/eid',[URL('/events/black-square-2027')])[0],'PASS_RETRIEVAL')
 def test_wrong_year_top1(self):
  self.assertEqual(check_output('top','/events/st-georges-day-2025',[URL('/events/st-georges-day-2024')])[0],'FAIL_WRONG_TOP1')
 def test_multiple_event_year(self):
  rs=[URL('/events/black-square-2027','Black On The Square 2027'),URL('/events/eid','Eid on the Square 2027')]
  self.assertEqual(check_output('year_many','2027',rs)[0],'PASS_RETRIEVAL')
  self.assertEqual(check_output('year_many','2027',rs[:1])[0],'FAIL_YEAR_DISCOVERY')
 def test_no_result_negative(self):
  self.assertEqual(check_output('no_result','',[])[0],'PASS_SAFETY')
  self.assertEqual(check_output('no_result','',[URL('/events/eid')])[0],'FAIL_FALSE_POSITIVE')
 def test_factual_not_graded_as_correct(self):
  self.assertEqual(check_output('fact_unverified','',[URL('/events/eid')])[0],'ABSTAIN_FACT_UNVERIFIED')
 def test_series_requires_multiple_same_series(self):
  rs=[URL('/events/london-open-house-2024','London Open House 2024'),URL('/events/city-hall-open-house-2026','City Hall Open House 2026')]
  self.assertEqual(check_output('series_many','london open house',rs)[0],'FAIL_SERIES_RECALL')
 def test_pin_constants(self):
  self.assertEqual(len(OWNER_SHA),64);self.assertEqual(len(R35_REPORT_SHA),64)
 def test_offline_missing_directory(self):
  with self.assertRaises(FileNotFoundError):PinnedSentenceEncoder('/there_is_no_approved_local_model_here')
 def test_model_requires_approval(self):
  with tempfile.TemporaryDirectory() as p:
   with self.assertRaises(ModelHold):PinnedSentenceEncoder(p)
 def test_model_hash_mismatch(self):
  with tempfile.TemporaryDirectory() as p:
   f=Path(p);(f/'PULSE_LICENSE_REVIEW_ACCEPTED.txt').write_text('APPROVED\n')
   (f/'config.json').write_text('{}')
   (f/'PULSE_APPROVED_MODEL.sha256').write_text('0'*64+'  config.json\n')
   with self.assertRaises(ModelHold):PinnedSentenceEncoder(p)
 def test_model_detects_unlisted_file(self):
  with tempfile.TemporaryDirectory() as p:
   f=Path(p);(f/'PULSE_LICENSE_REVIEW_ACCEPTED.txt').write_text('APPROVED\n')
   c=f/'config.json';c.write_text('{}'); (f/'unlisted.bin').write_bytes(b'Z')
   (f/'PULSE_APPROVED_MODEL.sha256').write_text(sha(c)+'  config.json\n')
   with self.assertRaises(ModelHold):PinnedSentenceEncoder(p)

if __name__=='__main__':unittest.main()
