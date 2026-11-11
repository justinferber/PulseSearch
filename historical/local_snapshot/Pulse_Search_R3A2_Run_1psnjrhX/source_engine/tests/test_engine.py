import functools
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pulse_search_engine as e

HTML_HEAD=b'<!DOCTYPE html><html><head>'
class Fixture(http.server.BaseHTTPRequestHandler):
    hits=[]
    robot_status=200
    refresh_version=1
    refresh_gone=False
    refresh_noindex=False
    refresh_robots_block=False
    refresh_304_noindex=False
    def log_message(self,*a):pass
    def do_GET(self):
        self.hits.append(self.path)
        paths={
          '/robots.txt':(200,'text/plain',b'User-agent: PulseSearchBot\nDisallow: /blocked\nAllow: /\n'),
          '/sitemap.xml':(200,'application/xml',b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>http://127.0.0.1:'+str(self.server.server_port).encode()+b'/guide</loc></url></urlset>'),
          '/':(200,'text/html',HTML_HEAD+b'<title>Pulse Search documentation home</title></head><body>Pulse Search independent engine explores public information safely. <a href="/guide">Guide</a><a href="/blocked">No</a><a href="https://other.example/">Offsite</a><a href="https://developer.mozilla.org/en-US/docs/Web/HTTP?tracking=123">MDN</a><a href="/private">Noindex</a></body></html>'),
          '/guide':(200,'text/html',HTML_HEAD+b'<title>Guide to independent internet search</title></head><body>Independent crawling and relevance ranking are explained in this useful guide.</body></html>'),
          '/duplicate':(200,'text/html',HTML_HEAD+b'<title>Guide to independent internet search</title></head><body>Independent crawling and relevance ranking are explained in this useful guide.</body></html>'),
          '/blocked':(200,'text/html',HTML_HEAD+b'<title>Blocked content</title></head><body>This must never be downloaded.</body></html>'),
          '/private':(200,'text/html',HTML_HEAD+b'<title>Secret private page</title><meta name="robots" content="noindex,nofollow"></head><body>Secret private page must not enter searchable index.</body></html>'),
          '/redirect-offsite':(302,'text/html',b''),
          '/redirect-in':(302,'text/html',b''),
          '/redirect-blocked':(302,'text/html',b''),
          '/canonical':(200,'text/html',HTML_HEAD+b'<title>Mirror content</title><link rel="canonical" href="/guide"></head><body>Mirror text should not be indexed as primary content.</body></html>'),
          '/header-noindex':(200,'text/html',HTML_HEAD+b'<title>Header private</title></head><body>Header private is hidden from index.</body></html>'),
          '/404':(404,'text/html',b'Not Found'),
        }
        if self.path=='/refresh':
            status,mime=200,'text/html'
            body=HTML_HEAD+b'<title>Refresh web search documentation</title></head><body>Version '+str(self.refresh_version).encode()+b' contains the '+(b'violetknight' if self.refresh_version==1 else b'aquamarinequeen')+b' search indexing information for responsible crawling.</body></html>'
            if self.refresh_noindex: body=HTML_HEAD+b'<title>Refresh web search</title><meta name="robots" content="noindex"></head><body>Data no longer permitted for indexing on this website.</body></html>'
            if self.refresh_gone:status,body=410,b'Gone'
            if status==200 and self.headers.get('If-None-Match')=='"v'+str(self.refresh_version)+'"' and not self.refresh_noindex:
                status,body=304,b''
        elif self.path=='/robots-500.txt': status,mime,body=500,'text/plain',b'broken'
        else: status,mime,body=paths.get(self.path,(404,'text/html',b'not found'))
        if self.path=='/robots.txt' and self.robot_status!=200:status,body=self.robot_status,b'error'
        if self.path=='/robots.txt' and self.refresh_robots_block and status==200:
            body=b'User-agent: PulseSearchBot\nDisallow: /refresh\nAllow: /\n'
        self.send_response(status);self.send_header('Content-Type',mime)
        if self.path=='/redirect-offsite':self.send_header('Location','https://example.org/hello')
        if self.path=='/redirect-in':self.send_header('Location','/guide')
        if self.path=='/redirect-blocked':self.send_header('Location','/blocked')
        if self.path=='/header-noindex':self.send_header('X-Robots-Tag','noindex')
        if self.path=='/refresh':self.send_header('ETag','"v'+str(self.refresh_version)+'"')
        if self.path=='/refresh' and status==304 and self.refresh_304_noindex:self.send_header('X-Robots-Tag','noindex')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)

class Suite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        cls.port=cls.httpd.server_port
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.port}'
    @classmethod
    def tearDownClass(cls):cls.httpd.shutdown();cls.thread.join();cls.httpd.server_close()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'index.db'; e.initdb(self.db)
        self.source={'source_id':'fixture','origin':self.base,'allowed_paths':['/'],
                     'collection_approved':True,'display_mode':'metadata_only',
                     'rights_basis':'Locally owned HTTP test fixture permits research indexing'}
        self.sfile=Path(self.tmp.name)/'sources.json';self.sfile.write_text(json.dumps([self.source]))
        Fixture.hits=[]
        Fixture.robot_status=200
        Fixture.refresh_version=1
        Fixture.refresh_gone=False
        Fixture.refresh_noindex=False
        Fixture.refresh_robots_block=False
        Fixture.refresh_304_noindex=False
    def crawl(self,seed='/',**kw):
        return e.crawl(self.db,self.sfile,[self.base+seed],allow_local=True,min_delay=0.01,**kw)
    def test_version(self):self.assertIn('r2p4',e.VERSION)
    def test_db_new_empty(self):
        with e.dbopen(self.db) as c:self.assertEqual(e.stats(c)['indexed_pages'],0)
    def test_url_reject_file(self):
        with self.assertRaises(e.Hold):e.normal_url('file:///etc/passwd')
    def test_url_reject_remote_http(self):
        with self.assertRaises(e.Hold):e.normal_url('http://example.com/')
    def test_url_reject_credentials(self):
        with self.assertRaises(e.Hold):e.normal_url('https://me:pw@example.com')
    def test_url_reject_bad_port(self):
        with self.assertRaises(e.Hold):e.normal_url('https://example.com:12345/')
    def test_url_strip_fragment(self):
        self.assertEqual(e.normal_url(self.base+'/guide#top',True),self.base+'/guide')
    def test_url_reject_dot_segment(self):
        with self.assertRaises(e.Hold):e.normal_url(self.base+'/a/%2e%2e/b',True)
    def test_dns_public_reject_private(self):
        with self.assertRaises(e.Hold):e.addresses('127.0.0.1',80)
    def test_dns_fixture_allows_loopback(self):
        self.assertEqual(e.addresses('127.0.0.1',self.port,True),['127.0.0.1'])
    def test_sources_require_approval(self):
        self.source['collection_approved']=False
        with self.assertRaises(e.Hold):e.validate_sources([self.source],True)
    def test_sources_require_rights_basis(self):
        self.source['rights_basis']='tbd'
        with self.assertRaises(e.Hold):e.validate_sources([self.source],True)
    def test_sources_license_snippets(self):
        self.source['display_mode']='licensed_snippet'
        with self.assertRaises(e.Hold):e.validate_sources([self.source],True)
    def test_sources_duplicate(self):
        with self.assertRaises(e.Hold):e.validate_sources([self.source,self.source],True)
    def test_scoped_path_boundaries(self):
        self.source['allowed_paths']=['/guide']
        with e.dbopen(self.db) as c:
            e.register_sources(c,[self.source],True)
            src=c.execute('SELECT * FROM sources').fetchone()
            self.assertTrue(e.scope(self.base+'/guide',src,True))
            self.assertFalse(e.scope(self.base+'/guideline',src,True))
    def test_scope_guards(self):
        with e.dbopen(self.db) as c:
            e.register_sources(c,[self.source],True)
            src=c.execute('SELECT * FROM sources').fetchone()
            self.assertFalse(e.scope('https://attacker.test/',src,True))
    def test_robots_disallow(self):
        r=self.crawl('/blocked',max_pages=1)
        self.assertIn('hold:robots_disallow',r['outcomes'])
        self.assertNotIn('/blocked',Fixture.hits)
    def test_robots_unavailable_503_fails_closed(self):
        Fixture.robot_status=503
        r=self.crawl('/guide',max_pages=1)
        self.assertEqual(r['index_pages'],0)
        self.assertTrue(next(iter(r['outcomes'])).startswith('hold:robots_http_503'))
        self.assertNotIn('/guide',Fixture.hits)
    def test_robots_missing_404_permits_scoped_crawl(self):
        Fixture.robot_status=404
        r=self.crawl('/guide',max_pages=1)
        self.assertEqual(r['index_pages'],1)
    def test_disallowed_redirect_is_not_fetched(self):
        r=self.crawl('/redirect-blocked',max_pages=1)
        self.assertIn('hold:redirect_robots_disallow',r['outcomes'])
        self.assertNotIn('/blocked',Fixture.hits)
    def test_crawl_seed_search(self):
        r=self.crawl('/',max_pages=4)
        self.assertEqual(r['index_pages'],2)
        with e.dbopen(self.db) as c:
            x=e.search(c,'relevance ranking')
            self.assertGreaterEqual(len(x),1)
            self.assertNotIn('snippet',x[0])
    def test_crawl_stages_outside_domain_without_network(self):
        r=self.crawl('/',max_pages=1)
        with e.dbopen(self.db) as c:
            candidate=c.execute("SELECT origin,example_url FROM external_candidates WHERE origin='https://developer.mozilla.org'").fetchone()
            self.assertIsNotNone(candidate)
            self.assertNotIn('tracking=123',candidate['example_url'])
            self.assertEqual(c.execute("SELECT COUNT(*) FROM sources WHERE origin='https://developer.mozilla.org'").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM frontier WHERE url LIKE 'https://developer.mozilla.org/%'").fetchone()[0],0)
        self.assertEqual(r['index_pages'],1)

    def test_noindex(self):
        r=self.crawl('/private',max_pages=1)
        self.assertEqual(r['index_pages'],0)
        with e.dbopen(self.db) as c:self.assertEqual(e.search(c,'secret private'),[])
    def test_x_robots_header(self):
        r=self.crawl('/header-noindex',max_pages=1)
        self.assertEqual(r['index_pages'],0)
    def test_canonical_not_self(self):
        r=self.crawl('/canonical',max_pages=1)
        self.assertEqual(r['index_pages'],0)
    def test_offsite_redirect_rejected(self):
        r=self.crawl('/redirect-offsite',max_pages=1)
        self.assertIn('hold:redirect_out_of_scope',r['outcomes'])
    def test_same_origin_redirect(self):
        r=self.crawl('/redirect-in',max_pages=1)
        self.assertEqual(r['index_pages'],1)
    def test_duplicate_content_not_reindexed(self):
        r=self.crawl('/guide',max_pages=1)
        r=e.crawl(self.db,self.sfile,[self.base+'/duplicate'],allow_local=True,min_delay=0.01,max_pages=1)
        self.assertEqual(r['index_pages'],1)
        self.assertEqual(r['outcomes']['duplicate'],1)
    def test_sitemap_extra_seed(self):
        r=self.crawl('/',max_pages=4,sitemaps=True)
        self.assertIn('/sitemap.xml',Fixture.hits)
        self.assertEqual(r['index_pages'],2)
    def test_malformed_xml_hold(self):
        with self.assertRaises(e.Hold):e.sitemap_links(b'<!DOCTYPE a [<!ENTITY x "abc">]><urlset></urlset>','x')
    def test_tokens_sql_safety(self):
        r=self.crawl('/guide',max_pages=1)
        with e.dbopen(self.db) as c:
            self.assertIsInstance(e.search(c,'" OR DROP TABLE pages; --'),list)
            self.assertEqual(e.stats(c)['indexed_pages'],1)
    def test_empty_search_invalid(self):
        with e.dbopen(self.db) as c:
            with self.assertRaises(e.Hold):e.search(c,'  ')
    def test_retire_source_hides_and_erases(self):
        self.crawl('/guide',max_pages=1)
        self.assertEqual(e.retire_source(self.db,'fixture'),1)
        with e.dbopen(self.db) as c:
            self.assertEqual(e.search(c,'independent crawling'),[])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM pages').fetchone()[0],0)
    def test_retire_promotes_duplicate_from_other_source(self):
        second=dict(self.source,source_id='fixture_2',origin=f'http://localhost:{self.port}')
        with e.dbopen(self.db) as c:
            e.register_sources(c,[self.source,second],True)
            s1=c.execute("SELECT * FROM sources WHERE source_id='fixture'").fetchone()
            s2=c.execute("SELECT * FROM sources WHERE source_id='fixture_2'").fetchone()
            a=e.index_page(c,self.base+'/guide',s1,'Search guide','Search engine independent crawling is useful','same-hash',True)
            b=e.index_page(c,second['origin']+'/guide',s2,'Search guide','Search engine independent crawling is useful','same-hash',True)
            self.assertEqual((a,b),('indexed','duplicate'))
        self.assertEqual(e.retire_source(self.db,'fixture'),1)
        with e.dbopen(self.db) as c:
            results=e.search(c,'independent crawling')
            self.assertEqual(len(results),1)
            self.assertIn('localhost',results[0]['url'])
    def test_page_update_removes_old_index_terms(self):
        with e.dbopen(self.db) as c:
            e.register_sources(c,[self.source],True)
            src=c.execute('SELECT * FROM sources').fetchone()
            e.index_page(c,self.base+'/guide',src,'Mars Search','Search engine for galactic events across space','first',True)
            e.index_page(c,self.base+'/guide',src,'Ocean Search','Search engine for maritime events across seas','second',True)
            self.assertEqual(e.search(c,'galactic'),[])
            self.assertEqual(len(e.search(c,'maritime')),1)
    def test_retired_source_does_not_autoreactivate(self):
        self.crawl('/guide',max_pages=1)
        e.retire_source(self.db,'fixture')
        with self.assertRaises(e.Hold):self.crawl('/guide',max_pages=1)
    def test_unauth_http_and_auth(self):
        self.crawl('/guide',max_pages=1)
        srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),e.make_handler(self.db,'unit-token-value-is-long-enough'))
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(srv.shutdown(),thread.join(),srv.server_close()))
        addr=f'http://127.0.0.1:{srv.server_port}/v1/search?q=internet'
        with self.assertRaises(HTTPError) as cm:urlopen(addr,timeout=4)
        self.assertEqual(cm.exception.code,401)
        cm.exception.close()
        with urlopen(Request(addr,headers={'Authorization':'Bearer unit-token-value-is-long-enough'}),timeout=4) as response:
            data=json.load(response)
        self.assertEqual(len(data['results']),1)
    def test_pagination_limit(self):
        self.crawl('/guide',max_pages=1)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),e.make_handler(self.db,'unit-token-value-is-long-enough'))
        th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
        self.addCleanup(lambda:(server.shutdown(),th.join(),server.server_close()))
        req=Request(f'http://127.0.0.1:{server.server_port}/v1/search?q=internet&limit=999',headers={'Authorization':'Bearer unit-token-value-is-long-enough'})
        with self.assertRaises(HTTPError) as cm:urlopen(req,timeout=4)
        self.assertEqual(cm.exception.code,400)
        cm.exception.close()
    def test_conditional_validator_on_first_fetch(self):
        r=self.crawl('/refresh',max_pages=1)
        self.assertEqual(r['outcomes'].get('indexed'),1)
        with e.dbopen(self.db) as c:
            self.assertEqual(c.execute('SELECT etag FROM fetch_validators').fetchone()[0],'"v1"')
    def test_reschedule_requires_elapsed_age(self):
        self.crawl('/refresh',max_pages=1)
        self.assertEqual(e.reschedule(self.db,24,1)['queued_for_revisit'],0)
    def test_304_revisit_preserves_index(self):
        self.crawl('/refresh',max_pages=1)
        self.assertEqual(e.reschedule(self.db,0,1)['queued_for_revisit'],1)
        r=self.crawl('/refresh',max_pages=1)
        self.assertEqual(r['outcomes'].get('not_modified_304'),1)
        with e.dbopen(self.db) as c:
            self.assertEqual(len(e.search(c,'violetknight')),1)
            self.assertEqual(c.execute('SELECT status FROM fetch_validators').fetchone()[0],304)
    def test_changed_page_replaces_index(self):
        self.crawl('/refresh',max_pages=1)
        e.reschedule(self.db,0,1)
        Fixture.refresh_version=2
        r=self.crawl('/refresh',max_pages=1)
        self.assertEqual(r['outcomes'].get('indexed'),1)
        with e.dbopen(self.db) as c:
            self.assertEqual(e.search(c,'violetknight'),[])
            self.assertEqual(len(e.search(c,'aquamarinequeen')),1)
    def test_unchanged_page_without_validator(self):
        self.crawl('/refresh',max_pages=1)
        with e.dbopen(self.db) as c:c.execute('DELETE FROM fetch_validators')
        e.reschedule(self.db,0,1)
        r=self.crawl('/refresh',max_pages=1)
        self.assertEqual(r['outcomes'].get('unchanged_content'),1)
    def test_deleted_page_removed_from_search(self):
        self.crawl('/refresh',max_pages=1)
        e.reschedule(self.db,0,1)
        Fixture.refresh_gone=True
        r=self.crawl('/refresh',max_pages=1)
        self.assertEqual(r['outcomes'].get('removed_or_denied_410'),1)
        with e.dbopen(self.db) as c:
            self.assertEqual(e.search(c,'violetknight'),[])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM fetch_validators').fetchone()[0],0)
    def test_noindex_on_revisit_removes_search_result(self):
        self.crawl('/refresh',max_pages=1)
        e.reschedule(self.db,0,1)
        Fixture.refresh_noindex=True
        r=self.crawl('/refresh',max_pages=1)
        self.assertEqual(r['outcomes'].get('not_indexed'),1)
        with e.dbopen(self.db) as c:self.assertEqual(e.search(c,'violetknight'),[])
    def test_robots_newly_blocks_revisit_and_removes_index(self):
        self.crawl('/refresh',max_pages=1)
        e.reschedule(self.db,0,1)
        Fixture.refresh_robots_block=True
        Fixture.hits=[]
        r=self.crawl('/refresh',max_pages=1)
        self.assertIn('hold:robots_disallow',r['outcomes'])
        self.assertNotIn('/refresh',Fixture.hits)
        with e.dbopen(self.db) as c:self.assertEqual(e.search(c,'violetknight'),[])
    def test_revisit_retirement_prevents_rescheduling(self):
        self.crawl('/refresh',max_pages=1)
        e.retire_source(self.db,'fixture')
        self.assertEqual(e.reschedule(self.db,0,1)['queued_for_revisit'],0)
    def test_revisit_rejects_unbounded_budget(self):
        with self.assertRaises(e.Hold):e.reschedule(self.db,0,10000)
    def test_older_database_can_be_migrated(self):
        with e.dbopen(self.db) as c:c.execute('DROP TABLE fetch_validators')
        e.initdb(self.db)
        with e.dbopen(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM fetch_validators').fetchone()[0],0)
    def test_deleting_original_promotes_duplicate(self):
        with e.dbopen(self.db) as c:
            e.register_sources(c,[self.source],True)
            src=c.execute('SELECT * FROM sources').fetchone()
            e.index_page(c,self.base+'/guide',src,'Search docs','This guide describes the aquatictype crawling and ranking system','same',True)
            e.index_page(c,self.base+'/duplicate',src,'Search docs','This guide describes the aquatictype crawling and ranking system','same',True)
            e.purge_page(c,self.base+'/guide')
            self.assertEqual([r['url'] for r in e.search(c,'aquatictype')],[self.base+'/duplicate'])
    def test_changing_original_promotes_duplicate(self):
        with e.dbopen(self.db) as c:
            e.register_sources(c,[self.source],True)
            src=c.execute('SELECT * FROM sources').fetchone()
            e.index_page(c,self.base+'/guide',src,'Search docs','This guide describes the aquatictype crawling and ranking system','same',True)
            e.index_page(c,self.base+'/duplicate',src,'Search docs','This guide describes the aquatictype crawling and ranking system','same',True)
            e.index_page(c,self.base+'/guide',src,'New docs','This guide describes the volcanoquest crawling and ranking system','different',True)
            self.assertEqual([r['url'] for r in e.search(c,'aquatictype')],[self.base+'/duplicate'])
            self.assertEqual([r['url'] for r in e.search(c,'volcanoquest')],[self.base+'/guide'])
    def test_noindex_header_on_304_invalidates(self):
        self.crawl('/refresh',max_pages=1)
        e.reschedule(self.db,0,1)
        Fixture.refresh_304_noindex=True
        r=self.crawl('/refresh',max_pages=1)
        self.assertEqual(r['outcomes'].get('not_indexed_304'),1)
        with e.dbopen(self.db) as c:self.assertEqual(e.search(c,'violetknight'),[])
    def test_budget_hard_limit(self):
        with self.assertRaises(e.Hold):self.crawl('/',max_pages=999)
    def test_live_delay_guard(self):
        with self.assertRaises(e.Hold): e.crawl(self.db,self.sfile,[],min_delay=0.0)

if __name__=='__main__':unittest.main()
