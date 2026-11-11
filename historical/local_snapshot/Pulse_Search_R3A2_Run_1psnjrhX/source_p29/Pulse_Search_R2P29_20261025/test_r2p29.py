import importlib.util
import json
from pathlib import Path
import unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('p29',HERE/'pulse_search_r2p29.py')
p29=importlib.util.module_from_spec(spec);spec.loader.exec_module(p29)

def entry(url,title,rank=0):return {'url':url,'title':title,'rank':rank,'source_id':'fixture'}

class ShadowTests(unittest.TestCase):
    def test_sources_bound_report(self):
        data=json.loads((HERE/'live_100_report.json').read_text())
        self.assertEqual((data['newly_indexed'],data['indexed_pages_after'],len(data['new_pages'])),(103,120,103))
    def test_matrix_bind_review(self):
        data=json.loads((HERE/'Pulse_Search_R2P23_Corrected_Reviewed.json').read_text())
        self.assertEqual([(x[0],x[1]) for x in p29.QUESTIONS],[(x['topic'],x['query']) for x in data['questions']])
    def test_london_nye_2026_vs_eid_2023(self):
        q=p29.QUESTIONS[6][1]
        candidates=[entry('https://www.london.gov.uk/events/eid-square-2023','Eid in the Square 2023 | London City Hall'),
                    entry('https://www.london.gov.uk/events/london-new-years-eve-2026','London New Year’s Eve 2026 | London City Hall')]
        hits,status,_=p29.shadow_rank(q,candidates)
        self.assertEqual(len(hits),1);self.assertTrue(hits[0]['url'].endswith('2026'))
    def test_nye_businesses_ranks_below_canonical(self):
        q=p29.QUESTIONS[6][1]
        cand=[entry('https://www.london.gov.uk/events/london-new-years-eve-2026/london-new-years-eve-2026-information-businesses-and-residents','London New Year’s Eve 2026: Information for businesses and residents | London City Hall'),entry('https://www.london.gov.uk/events/london-new-years-eve-2026','London New Year’s Eve 2026 | London City Hall')]
        hits,_,_=p29.shadow_rank(q,cand)
        self.assertEqual(len(hits),2);self.assertEqual(hits[0]['url'],'https://www.london.gov.uk/events/london-new-years-eve-2026')
    def test_diwali_wrong_year_rejected(self):
        q=p29.QUESTIONS[7][1]
        pool=[entry(f'https://www.london.gov.uk/events/diwali-square-{y}',f'Diwali on the Square {y} | London City Hall') for y in (2025,2023,2026)]
        hits,_,excluded=p29.shadow_rank(q,pool)
        self.assertEqual(len(hits),1);self.assertEqual(hits[0]['url'],pool[2]['url']);self.assertEqual(len(excluded),2)
    def test_lunar_new_year_not_nye(self):
        q=p29.QUESTIONS[6][1]
        row=entry('https://www.london.gov.uk/events/lunar-new-year-festival-spring-2026','Lunar New Year - the Festival of Spring 2026 | London City Hall')
        self.assertEqual(p29.shadow_rank(q,[row])[0],[])
    def test_year_in_body_not_just_title(self):
        q=p29.QUESTIONS[7][1]
        row=entry('https://www.london.gov.uk/events/diwali-square-2025','Diwali on the Square 2025 | London City Hall')
        self.assertFalse(p29.title_score(q,row['title'],row['url'])[0])
    def test_council_tax_noise_removed(self):
        q=p29.QUESTIONS[2][1]
        pool=[entry('https://www.gov.uk/council-tax-bands','Check your Council Tax band - GOV.UK'),entry('https://www.london.gov.uk/events/diwali-square-2026','Diwali on the Square 2026 | London City Hall'),entry('https://www.gov.uk/register-to-vote','Register to vote - GOV.UK')]
        hits,_,_=p29.shadow_rank(q,pool)
        self.assertEqual([x['url'] for x in hits],[pool[0]['url']])
    def test_nhs_avoids_dentist(self):
        q=p29.QUESTIONS[0][1]
        pool=[entry('https://www.nhs.uk/tests-and-treatments/blood-tests/','Blood tests - NHS'),entry('https://www.nhs.uk/nhs-services/dentists/how-to-find-an-nhs-dentist/','How to find an NHS dentist')]
        hits,_,_=p29.shadow_rank(q,pool);self.assertEqual(len(hits),1)
    def test_gp_prescriptions_removed(self):
        q=p29.QUESTIONS[1][1]
        pool=[entry('https://www.nhs.uk/nhs-services/gps/how-to-register-with-a-gp-surgery/','Register with a GP surgery - NHS'),entry('https://www.nhs.uk/nhs-services/prescriptions/how-to-order-a-repeat-prescription/','How to order a repeat prescription - NHS')]
        self.assertEqual(len(p29.shadow_rank(q,pool)[0]),1)
    def test_http_not_robots(self):
        q=p29.QUESTIONS[5][1]
        pool=[entry('https://developer.mozilla.org/en-US/docs/Web/HTTP','HTTP: Hypertext Transfer Protocol | MDN'),entry('https://www.rfc-editor.org/rfc/rfc9309.html','RFC 9309: Robots Exclusion Protocol')]
        self.assertEqual(len(p29.shadow_rank(q,pool)[0]),1)
    def test_javascript_not_python(self):
        q=p29.QUESTIONS[4][1]
        pool=[entry('https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Scripting/What_is_JavaScript','What is JavaScript? - Learn web development | MDN'),entry('https://docs.python.org/3/tutorial/index.html','The Python Tutorial — Python documentation')]
        self.assertEqual(len(p29.shadow_rank(q,pool)[0]),1)
    def test_identity_separates_passport_and_licence(self):
        q=p29.QUESTIONS[9][1]
        pool=[entry('https://www.gov.uk/apply-first-provisional-driving-licence','Apply for your first provisional driving licence'),entry('https://www.gov.uk/renew-adult-passport/renew','Renew or replace your adult passport: Renew - GOV.UK')]
        self.assertEqual(len(p29.shadow_rank(q,pool)[0]),1)
    def test_dynamic_live_queries_abstain(self):
        for q in (p29.QUESTIONS[10][1],p29.QUESTIONS[11][1]):
            results,status,_=p29.shadow_rank(q,[entry('https://www.london.gov.uk/events/black-square-2026','Black on the Square')]);self.assertEqual(results,[]);self.assertEqual(status,'WITHHELD_UNVERIFIED_LIVE_DATA')
    def test_weather_static_unsupported(self):self.assertTrue(p29.dynamic_intent('Will it rain in Newbury tomorrow?'))
    def test_year_regex_boundary(self):
        self.assertEqual(p29.YEARS.findall('Year 2026'),['2026']);self.assertEqual(p29.YEARS.findall('20262'),[])
    def test_no_title_support_abstain(self):
        result=p29.shadow_rank('Where can I register to vote?',[entry('https://www.london.gov.uk/events/diwali-square-2026','Diwali on the Square 2026')]);self.assertEqual(result[0],[])
    def test_sham_source_never_full_score(self):
        # Passing a page because it shares only a vague word must not happen.
        self.assertFalse(p29.title_score('How do I renew my UK adult passport online?','Apply for your first provisional driving licence','https://www.gov.uk/apply-first-provisional-driving-licence')[0])
    def test_score_deterministic_order(self):
        q=p29.QUESTIONS[5][1];rows=[entry('https://developer.mozilla.org/docs/HTTP','HTTP documentation',0),entry('https://test.example/HTTP','HTTP documentation',0)]
        self.assertEqual(p29.shadow_rank(q,rows)[0],p29.shadow_rank(q,list(reversed(rows)))[0])
    def test_manifest_has_no_production_outputs(self):self.assertFalse((HERE/'expanded_live_100_research_index.sqlite').exists())

if __name__=='__main__':unittest.main()
