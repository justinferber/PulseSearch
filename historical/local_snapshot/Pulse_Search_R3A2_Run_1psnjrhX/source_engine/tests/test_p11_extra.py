import json, hashlib, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pulse_search_engine as e
import pulse_search_real_questions as r9
import pulse_search_p11 as m

class EndToEndBinding(unittest.TestCase):
    def test_full_readonly_owner_style_audit_fixture(self):
        with tempfile.TemporaryDirectory() as t:
            db=Path(t)/'db.sqlite'
            e.initdb(db)
            with e.dbopen(db) as c:
                e.register_sources(c,[{'source_id':'technical_docs','origin':'https://docs.python.org/','allowed_paths':['/3/'], 'collection_approved':True,'display_mode':'metadata_only','rights_basis':'Synthetic fixture internal only; no live external rights involved.'}])
                c.execute('INSERT INTO pages(id,url,source_id,title,body,content_sha256,fetched_at,duplicate_of,indexed) VALUES(?,?,?,?,?,?,?,?,?)',(1,'https://docs.python.org/3/tutorial/index.html','technical_docs','Python Tutorial','Learn Python programming using Python tutorial.','synthetic','2026-10-22T00:00:00Z',None,1))
                c.execute('INSERT INTO page_fts(rowid,title,body) VALUES(?,?,?)',(1,'Python Tutorial','Learn Python programming using Python tutorial.'))
            with __import__("contextlib").closing(m.p10.read_only_db(db)) as c:
                fingerprint=r9.digest([dict(r) for r in c.execute('SELECT url,source_id,title,content_sha256,indexed FROM pages ORDER BY url')])
            qs=[{'id':'q%02d'%i,'q':q, 'results':[{'url':'https://docs.python.org/3/tutorial/index.html','position':1}]} for i,q in enumerate(['What is Python tutorial?']*8+['Which restaurants near me are open now?'],1)]
            candidate={'questions':qs,'fingerprint':fingerprint}
            candidate['results_sha256']=r9.digest(candidate)
            review={'results_sha256':candidate['results_sha256'],'index_fingerprint':fingerprint,
                    'questions':[{'id':q['id'],'judgements':[{'url':'https://docs.python.org/3/tutorial/index.html','position':1,'grade':2 if q['id']!='q09' else 0,'answered':False}]} for q in qs]}
            before=hashlib.sha256(db.read_bytes()).hexdigest()
            report=m.compare_real_review(db,candidate,review)
            self.assertEqual(len(report['questions']),9)
            self.assertTrue(report['regression']['q09_no_indexed_match'])
            self.assertEqual(m.api_smoke(db)['http_unauthorised'],401)
            self.assertEqual(before,hashlib.sha256(db.read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
