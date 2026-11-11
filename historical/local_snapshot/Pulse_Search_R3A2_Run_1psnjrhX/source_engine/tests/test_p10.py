import sys,unittest,tempfile,sqlite3,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pulse_search_p10 as p
import pulse_search_engine as e
import pulse_search_real_questions as rq

class Tests(unittest.TestCase):
    def test_review_counts(self):
        x=p.review_metrics(p.load_json(ROOT/'owner_review_original.json'))
        self.assertEqual((x['queries'],x['graded_results'],x['useful_top1'],x['irrelevant_results'],x['answer_flag_conflicts']), (9,27,7,16,20))
        self.assertEqual(x['answer_rate_status'],'UNRELIABLE_REQUIRES_HUMAN_RECHECK')
    def test_keywords(self):
        self.assertEqual(p.tokenize('Which restaurants near me are open now?'),['restaurants','open'])
        self.assertEqual(p.tokenize('What is HTTP?'),['http'])
    def test_ranked_experiment_and_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'test.sqlite';e.initdb(db)
            source={'source_id':'technical_docs','origin':'https://docs.python.org/', 'allowed_paths':['/3/'], 'collection_approved':True, 'display_mode':'metadata_only', 'rights_basis':'Synthetic fixture only for read-only unit tests.'}
            with e.dbopen(db) as c:
                e.register_sources(c,[source])
                samples=[('https://docs.python.org/3/tutorial/index.html','Python tutorial','Learn Python programming using Python tutorial.'),
                ('https://docs.python.org/3/other/open.html','Open a file','Open programming files from Python documentation')]
                for idx,(url,title,body) in enumerate(samples,1):
                    c.execute('INSERT INTO pages(id,url,source_id,title,body,content_sha256,fetched_at,duplicate_of,indexed) VALUES(?,?,?,?,?,?,?,?,?)',(idx,url,'technical_docs',title,body,hashlib.sha256(body.encode()).hexdigest(),'2026-10-22T00:00:00Z',None,1))
                    c.execute('INSERT INTO page_fts(rowid,title,body) VALUES(?,?,?)',(idx,title,body))
            before=hashlib.sha256(db.read_bytes()).hexdigest()
            with p.read_only_db(db) as conn:
                self.assertEqual(p.ranked_experiment(conn,'Which restaurants near me are open now?'),[])
                hits=p.ranked_experiment(conn,'Where can I learn Python programming?')
                self.assertTrue(hits)
                self.assertIn('tutorial',hits[0]['url'])
                with self.assertRaises(sqlite3.OperationalError):conn.execute('DELETE FROM pages')
            after=hashlib.sha256(db.read_bytes()).hexdigest()
            self.assertEqual(before,after)
    def test_changed_candidate_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'test.sqlite';e.initdb(db)
            doc={'questions':[{'id':f'q{i:02d}','results':[]} for i in range(1,10)],'fingerprint':'bogus','results_sha256':'mismatch'}
            with p.read_only_db(db) as conn:
                with self.assertRaisesRegex(p.GateError,'candidate_collection_hash_mismatch'):
                    p.validate_bindings(doc,{},conn)
    def test_unchanged_full_binding(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'test.sqlite';e.initdb(db)
            with p.read_only_db(db) as conn:
                finger=rq.digest([dict(r) for r in conn.execute('SELECT url,source_id,title,content_sha256,indexed FROM pages ORDER BY url')])
                doc={'version':'r2p9','questions':[{'id':f'q{i:02d}','results':[]} for i in range(1,10)],'fingerprint':finger}
                doc['results_sha256']=rq.digest(doc)
                review={'results_sha256':doc['results_sha256'],'index_fingerprint':finger,'questions':[{'id':f'q{i:02d}','judgements':[]} for i in range(1,10)]}
                p.validate_bindings(doc,review,conn)
    def test_grade_known_unjudged(self):
        prev=[{'url':'https://a.test','grade':2}]
        self.assertEqual(p.measure_known({},prev,[{'url':'https://b.test'}])['status'],'REVIEW_REQUIRED')
        self.assertEqual(p.measure_known({},prev,[{'url':'https://a.test'}])['top1_useful'],True)

if __name__=='__main__':unittest.main()
