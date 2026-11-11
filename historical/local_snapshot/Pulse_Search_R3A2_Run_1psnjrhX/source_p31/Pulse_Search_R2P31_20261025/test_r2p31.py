import json, sys, unittest
from pathlib import Path
import pulse_search_r2p31 as r

DIR=Path(__file__).resolve().parent
PROXY=json.loads((DIR/'metadata_proxy.json').read_text())
R30=json.loads((DIR/'r2p30_recall_report.json').read_text())
R29=json.loads((DIR/'r2p29_shadow_report.json').read_text())

# These expected URLs are TEST oracle data, never imported by the ranker.
EXPECTED_PARAPHRASE={
 'How do I get an NHS blood test?':'https://www.nhs.uk/tests-and-treatments/blood-tests/',
 'How to sign up with a family doctor surgery?':'https://www.nhs.uk/nhs-services/gps/how-to-register-with-a-gp-surgery/',
 'Check the property tax band of my home':'https://www.gov.uk/council-tax-bands',
 'Getting started learning JS coding':'https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Scripting/What_is_JavaScript',
 'How can I apply for a learner driver permit in Britain?':'https://www.gov.uk/apply-first-provisional-driving-licence',
 'Tell me about London City Hall New Year fireworks 2026':'https://www.london.gov.uk/events/london-new-years-eve-2026',
}
BROAD_MIN={'London events 2027':3,'Which festivals are happening in London in 2026?':3,
 'What happened during London Open House over the years?':3,
 'What London celebrations were held in 2025?':3,
 'What online government services can I use?':3}

class R2P31ProxyTests(unittest.TestCase):
 def test_source_fixture_size(self):
  self.assertGreaterEqual(len(PROXY),115)
  self.assertEqual(len(PROXY),len({p['url'] for p in PROXY}))
 def test_eight_named_edition_top1(self):
  for q in R30['questions']:
   if q['group']!='named_edition':continue
   with self.subTest(q=q['query']):
    res,_,_=r.rank(q['query'],PROXY)
    self.assertTrue(res)
    self.assertEqual(res[0]['url'],q['expected_source_url'])
 def test_six_paraphrase_top1(self):
  for q,url in EXPECTED_PARAPHRASE.items():
   with self.subTest(q=q):
    found,_,_=r.rank(q,PROXY)
    self.assertTrue(found);self.assertEqual(found[0]['url'],url)
 def test_five_broad_discovery(self):
  for q,n in BROAD_MIN.items():
   with self.subTest(q=q):
    hits,_,_=r.rank(q,PROXY)
    self.assertGreaterEqual(len(hits),n)
    if 2027 in [int(x) for x in r.YEAR_RE.findall(q)]:
     self.assertTrue(all('2027' in h['title'] for h in hits))
 def test_five_controls(self):
  for row in R30['questions']:
   if row['group']=='negative_control':
    with self.subTest(q=row['query']):self.assertFalse(r.rank(row['query'],PROXY)[0])
 def test_prior_12_first_titles(self):
  for row in R29['questions']:
   with self.subTest(q=row['query']):
    found,_,_=r.rank(row['query'],PROXY)
    if row['shadow']:
     self.assertTrue(found);self.assertEqual(found[0]['url'],row['shadow'][0]['url'])
    else:self.assertFalse(found)
 def test_url_anchors_no_answer_substitution(self):
  for q in ['Black on the Square 2031','Armed Forces Day 2031','Black on the Square 2027']:
   found,_,_=r.rank(q,PROXY)
   if '2031' in q:self.assertFalse(found)
   else:self.assertEqual(found[0]['url'],'https://www.london.gov.uk/events/black-square-2027')
 def test_live_questions_abstain(self):
  for q in ['Are shops open now in Manchester?', 'Will it rain tomorrow?', 'Is a new laptop in stock today?']:
   self.assertFalse(r.rank(q,PROXY)[0])
 def test_retrieval_not_truth_status(self):
  hits,status,spec=r.rank('How to sign up with a family doctor surgery?',PROXY)
  self.assertEqual(status,'MATCHES_UNVERIFIED')
  self.assertNotIn('verified',hits[0]['match_reason'].lower())

if __name__=='__main__':unittest.main()

# Fresh probing phrases are deliberately absent from R2-P30; they check that
# alias rules apply to variants, instead of mapping the 8 failed queries to URLs.
HELDOUT=(
 ('Eid on the Square 2026','/events/eid-square-2026'),
 ('Remembrance Service 2026','/events/remembrance-service-2026'),
 ('Armed Forces Day 2025','/events/armed-forces-day-2025'),
 ('UK Black Pride 2024','/events/uk-black-pride-2024'),
 ('What do I need to register with GP?','/how-to-register-with-a-gp-surgery/'),
 ('NHS GP surgery registration','/how-to-register-with-a-gp-surgery/'),
 ('How to check council tax band','/council-tax-bands'),
 ('How do I register to vote online?','/register-to-vote'),
 ('What is JavaScript','/What_is_JavaScript'),
 ('Intro to HTTP protocol','/Web/HTTP'),
 ('Britain provisional driving licence application','/apply-first-provisional-driving-licence'),
 ('How to renew adult passport','/renew-adult-passport/renew'),
 ('London New Year Eve 2026','/events/london-new-years-eve-2026'),
 ('Black on the Square 2030',None),
 ('London festivals 2040',None),
 ('Will it snow tomorrow?',None),
 ('London events in 2026','YEAR_2026'),
 ('London festivals 2027','YEAR_2027_FESTIVAL'),
 ('Government services online','GOV_SERVICES'),
 ('History of UK Black Pride','UK_BLACK_PRIDE'),
)

class R2P31HeldoutTests(unittest.TestCase):
 def test_twenty_unseen_phrases(self):
  from urllib.parse import urlsplit
  for query,expected in HELDOUT:
   with self.subTest(query=query):
    matches,stat,spec=r.rank(query,PROXY)
    if expected is None:self.assertFalse(matches)
    elif expected=='YEAR_2026':
     self.assertGreaterEqual(len(matches),3)
     self.assertTrue(all('2026' in v['title'] for v in matches))
    elif expected=='YEAR_2027_FESTIVAL':
     self.assertTrue(matches)
     self.assertTrue(all('2027' in v['title'] and 'Festival' in v['title'] for v in matches))
    elif expected=='GOV_SERVICES':
     self.assertGreaterEqual(len(matches),3)
     self.assertTrue(all(urlsplit(v['url']).netloc=='www.gov.uk' for v in matches))
    elif expected=='UK_BLACK_PRIDE':
     self.assertGreaterEqual(len(matches),2)
     self.assertTrue(all('UK Black Pride' in v['title'] for v in matches))
    else:
     self.assertTrue(matches)
     self.assertIn(expected,matches[0]['url'])
