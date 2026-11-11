import hashlib, json, sqlite3, sys, tempfile, unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
import secrets, threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pulse_search_p11 as m
import pulse_search_p10 as p
import pulse_search_engine as e

class P11Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'s.sqlite'
        e.initdb(self.db)
        with e.dbopen(self.db) as c:
            e.register_sources(c,[{'source_id':'technical_docs','origin':'https://docs.python.org/','allowed_paths':['/3/'],
                                  'collection_approved':True,'display_mode':'metadata_only',
                                  'rights_basis':'Synthetic local unit test data; no real internet resource.'}])
            c.execute('INSERT INTO pages(id,url,source_id,title,body,content_sha256,fetched_at,duplicate_of,indexed) VALUES(?,?,?,?,?,?,?,?,?)',
                (1,'https://docs.python.org/3/tutorial/index.html','technical_docs','Python Tutorial',
                 'Learn Python programming using Python tutorial.','unit-hash','2026-10-22T00:00:00Z',None,1))
            c.execute('INSERT INTO page_fts(rowid,title,body) VALUES(?,?,?)',(1,'Python Tutorial','Learn Python programming using Python tutorial.'))
    def tearDown(self):self.temp.cleanup()
    def test_query_validation(self):
        self.assertEqual(m.validate_query({'q':['Python programming']}),('Python programming',3))
        for query in ({'q':['']},{'q':['x']*2},{'q':['a'*257]},{'q':['ok'],'limit':['0']},{'q':['ok'],'limit':['11']},{'q':['ok'],'extra':['s']},{'q':['ok'],'limit':['x']}):
            with self.assertRaises(m.ApiInputError):m.validate_query(query)
    def test_search_is_index_only(self):
        before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        res=m.search_payload(self.db,'Where can I learn Python programming?')
        self.assertEqual(res['coverage_status'],'MATCHES_FOUND_NOT_VERIFIED_ANSWERS')
        self.assertEqual(res['results'][0]['source_id'],'technical_docs')
        self.assertFalse(res['production_approved'])
        self.assertFalse(res['answer_verified'])
        self.assertEqual(before,hashlib.sha256(self.db.read_bytes()).hexdigest())
    def test_no_match_honest(self):
        res=m.search_payload(self.db,'Which restaurants near me are open now?')
        self.assertEqual(res['coverage_status'],'NO_INDEXED_MATCH')
        self.assertEqual(res['results'],[])
        self.assertIn('does not mean',res['disclaimer'])
    def test_bad_http_auth_and_valid(self):
        token=secrets.token_urlsafe(30)
        srv=ThreadingHTTPServer(('127.0.0.1',0),m.make_handler(self.db,token))
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(srv.server_address[1])
        try:
            with self.assertRaises(HTTPError) as cm:
                urlopen(base+'/v1/experimental/search?q=Python',timeout=3)
            self.assertEqual(cm.exception.code,401);cm.exception.close()
            with urlopen(Request(base+'/v1/experimental/search?q=Python',headers={'Authorization':'Bearer '+token}),timeout=3) as r:
                self.assertEqual(r.status,200)
                self.assertEqual(json.load(r)['results'][0]['title'],'Python Tutorial')
        finally:
            srv.shutdown();thread.join(timeout=3);srv.server_close()
    def test_strict_json_binding(self):
        with p.read_only_db(self.db) as c:
            with self.assertRaisesRegex(p.GateError,'candidate_collection_hash_mismatch'):
                p.validate_bindings({'results_sha256':'bad'}, {}, c)
    def test_fully_irrelevant_does_not_claim_answer(self):
        self.assertFalse(m.search_payload(self.db,'restaurants now')['answer_verified'])

if __name__=='__main__':unittest.main()
