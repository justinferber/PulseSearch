import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pulse_search_real_questions as r
import pulse_search_engine as e

class RealQuestionTests(unittest.TestCase):
    def test_real_plan(self):
        sources,seeds,qs=r.validate_plan()
        self.assertEqual((len(sources),len(seeds),len(qs)),(7,8,9))
        self.assertEqual(len({x['id'] for x in qs}),9)
    def test_unapproved_rejected(self):
        s,seed,qs=r.validate_plan();s[0]['collection_approved']=False
        with self.assertRaises(e.Hold):r.validate_plan(s,seed,qs)
    def test_expanded_scope_rejected(self):
        s,seed,qs=r.validate_plan();seed[0]='https://unknown.example/robots.txt'
        with self.assertRaises(e.Hold):r.validate_plan(s,seed,qs)
    def test_extra_seed_rejected(self):
        s,seed,qs=r.validate_plan();seed.append('https://www.gov.uk/renew-adult-passport/renew?v=1')
        with self.assertRaises(e.Hold):r.validate_plan(s,seed,qs)
    def test_duplicate_queries_rejected(self):
        s,seed,qs=r.validate_plan();qs[1]['id']=qs[0]['id']
        with self.assertRaises(e.Hold):r.validate_plan(s,seed,qs)
    def fixture(self,t):
        body={'version':r.VERSION,'fingerprint':'abcd','questions':[{'id':'q01','q':"How to renew a UK passport?",'category':'government','answer_intent':'Official renewal guidance','results':[{'url':'https://www.gov.uk/renew-adult-passport/renew','title':'Passport &amp; renewal','position':1,'source_id':'uk_passport','fetched_at':'now'}]}]}
        body['results_sha256']=r.digest({k:v for k,v in body.items() if k!='results_sha256'})
        f=Path(t)/'candidate.json';f.write_text(json.dumps(body))
        review={'version':'r2p9-human-review','results_sha256':body['results_sha256'],'index_fingerprint':'abcd','questions':[{'id':'q01','judgements':[{'url':body['questions'][0]['results'][0]['url'],'position':1,'grade':3,'answered':True}]}]}
        g=Path(t)/'review.json';g.write_text(json.dumps(review));return body,review,f,g
    def test_valid_human_scores(self):
        with tempfile.TemporaryDirectory() as t:
            _,_,f,g=self.fixture(t)
            s=r.score(f,g)
            self.assertEqual(s['queries_with_answer_in_top3'],1)
            self.assertEqual(s['mean_ndcg_at_3'],1.0)
    def test_missing_grade_fails(self):
        with tempfile.TemporaryDirectory() as t:
            _,review,f,g=self.fixture(t)
            review['questions'][0]['judgements'][0]['grade']=None;g.write_text(json.dumps(review))
            with self.assertRaises(e.Hold):r.score(f,g)
    def test_wrong_url_fails(self):
        with tempfile.TemporaryDirectory() as t:
            _,review,f,g=self.fixture(t)
            review['questions'][0]['judgements'][0]['url']='https://bad.example';g.write_text(json.dumps(review))
            with self.assertRaises(e.Hold):r.score(f,g)
    def test_wrong_hash_fails(self):
        with tempfile.TemporaryDirectory() as t:
            _,review,f,g=self.fixture(t)
            review['results_sha256']='0'*64;g.write_text(json.dumps(review))
            with self.assertRaises(e.Hold):r.score(f,g)
    def test_html_escaping(self):
        body={'fingerprint':'123','results_sha256':'456','questions':[{'id':'q01','q':'X <script>alert(1)</script>','category':'other','answer_intent':'Find <b> text','results':[{'title':'<script>alert(2)</script>','url':'https://safe.example/a?x=1&y=2','position':1}]}]}
        h=r.review_html(body)
        self.assertNotIn('<script>alert(2)</script>',h)
        self.assertIn('&lt;script&gt;alert(2)&lt;/script&gt;',h)
        self.assertIn('Search: X &lt;script&gt;',h)
    def test_no_results_scoring(self):
        with tempfile.TemporaryDirectory() as t:
            _,review,f,g=self.fixture(t)
            source=json.loads(f.read_text());source['questions'][0]['results']=[];source['results_sha256']=r.digest({k:v for k,v in source.items() if k!='results_sha256'})
            review['questions'][0]['judgements']=[];review['results_sha256']=source['results_sha256']
            f.write_text(json.dumps(source));g.write_text(json.dumps(review))
            score=r.score(f,g)
            self.assertEqual(score['no_result_queries'],1)
            self.assertIsNone(score['mean_ndcg_at_3'])
    def test_read_only_without_approval(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(e.Hold):r.run_benchmark(Path(t)/'db.sqlite',Path(t)/'new',live=False)
            self.assertFalse((Path(t)/'db.sqlite').exists())

if __name__=='__main__':unittest.main()
