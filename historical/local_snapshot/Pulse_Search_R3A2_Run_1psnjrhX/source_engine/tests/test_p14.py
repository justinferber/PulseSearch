import gzip
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlsplit
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pulse_search_p14 as p14
import pulse_search_engine as e


def sitemap_xml(*urls, kind='urlset'):
    if kind=='urlset':
        return ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+
                ''.join('<url><loc>'+u+'</loc></url>' for u in urls)+'</urlset>').encode()
    return ('<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+
            ''.join('<sitemap><loc>'+u+'</loc></sitemap>' for u in urls)+'</sitemapindex>').encode()


class Fixture(http.server.BaseHTTPRequestHandler):
    responses = {}
    seen = []
    def log_message(self,*args):pass
    def do_GET(self):
        self.seen.append(self.path)
        status, mime, body, extra = self.responses.get(self.path,(404,'text/plain',b'404',{}))
        self.send_response(status)
        self.send_header('Content-Type',mime)
        for k,v in extra.items(): self.send_header(k,v)
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Unit(unittest.TestCase):
    def test_declarations_case_comment_duplicate(self):
        robots=b'Sitemap: https://example.com/index.xml # ignored\nsitemap: https://example.com/index.xml\nSITEMAP: https://others.org/no.xml\n'
        self.assertEqual(p14.declared_sitemaps(robots,'https://example.com'),['https://example.com/index.xml'])
    def test_no_network_and_credentials(self):
        robots=b'Sitemap: http://127.0.0.1/internal\nSitemap: https://a:b@example.com/secret.xml\n'
        self.assertEqual(p14.declared_sitemaps(robots,'https://example.com'),[])
    def test_parse_index(self):
        kind,urls=p14.parse_sitemap(sitemap_xml('https://site.org/a.xml',kind='sitemapindex'),'https://site.org/index.xml')
        self.assertEqual((kind,urls),('sitemapindex',['https://site.org/a.xml']))
    def test_parse_urlset_namespaced(self):
        kind,urls=p14.parse_sitemap(sitemap_xml('https://site.org/events/1'),'https://site.org/sitemap.xml')
        self.assertEqual((kind,urls),('urlset',['https://site.org/events/1']))
    def test_ignore_image_loc(self):
        x=b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><image:image xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"><image:loc>https://evil.org/x</image:loc></image:image><loc>https://site.org/events/yes</loc></url></urlset>'
        self.assertEqual(p14.parse_sitemap(x,'https://site.org/sitemap.xml')[1],['https://site.org/events/yes'])
    def test_gzip(self):
        x=sitemap_xml('https://site.org/events/nye')
        self.assertEqual(p14.parse_sitemap(gzip.compress(x),'https://site.org/site.xml.gz')[1],['https://site.org/events/nye'])
    def test_gzip_over_limit(self):
        x=gzip.compress(b'A'*(p14.MAX_EXPANDED_BYTES+1))
        with self.assertRaisesRegex(e.Hold,'decompressed_size_limit'):
            p14.decode_sitemap(x,'https://site.org/s.xml.gz','','')
    def test_doctype_rejected(self):
        x=b'<!DOCTYPE foo [<!ENTITY x "xx">]><urlset></urlset>'
        with self.assertRaisesRegex(e.Hold,'dtd_forbidden'):p14.parse_sitemap(x,'https://site.org/x.xml')
    def test_malformed_fails_closed(self):
        with self.assertRaisesRegex(e.Hold,'invalid_sitemap_xml'):p14.parse_sitemap(b'<urlset><url>','https://site.org/x.xml')
    def test_invalid_root_rejected(self):
        with self.assertRaisesRegex(e.Hold,'unsupported_sitemap_root'):p14.parse_sitemap(b'<rss/>','https://site.org/rss')
    def test_non_xml_encoding_rejected(self):
        with self.assertRaisesRegex(e.Hold,'unsupported_sitemap_encoding'):p14.parse_sitemap(b'\xff\xfe<\x00','https://site.org/sitemap.xml')
    def test_priority_event_sitemaps(self):
        x=['https://site.org/sitemap-news.xml','https://site.org/events-sitemap.xml']
        self.assertIn('events',sorted(x,key=lambda u:p14._sitemap_priority(u,'events 2026'))[0])
    def test_score_page(self):
        a=p14.query_score('https://site.org/events/london-new-years-eve-2026','What events London New Years Eve 2026')
        b=p14.query_score('https://site.org/events/site-guidelines','What events London New Years Eve 2026')
        self.assertGreater(a,b)
    def test_same_origin_guard(self):
        src={'origin':'https://example.org'}
        self.assertIsNone(p14._valid_sitemap_doc('https://another.org/sitemap.xml',src))
        self.assertIsNone(p14._valid_sitemap_doc('https://example.org/sitemap.xml?token=123',src))
    def test_paged_sitemap_query_permitted(self):
        src={'origin':'https://example.org'}
        self.assertEqual(p14._valid_sitemap_doc('https://example.org/sitemap.xml?page=0',src),
                         'https://example.org/sitemap.xml?page=0')
        self.assertEqual(p14._valid_sitemap_doc('https://example.org/sitemap.xml?type=default&page=14',src),
                         'https://example.org/sitemap.xml?type=default&page=14')
    def test_query_guards_for_sitemap(self):
        src={'origin':'https://example.org'}
        for q in ('token=abc','page=-1','page=100001','page=00','page=1&page=2','type=a&token=x',
                  'type=a&type=b','page=x','type=../../secret'):
            with self.subTest(q=q):
                self.assertIsNone(p14._valid_sitemap_doc('https://example.org/sitemap.xml?'+q,src))
        self.assertIsNone(p14._valid_sitemap_doc('https://other.org/sitemap.xml?page=0',src))
        self.assertIsNone(p14._valid_sitemap_doc('https://example.org/events/secret?page=0',src))
    def test_declared_paged_sitemap(self):
        raw=b'Sitemap: https://example.org/sitemap.xml?page=1\n'
        self.assertEqual(p14.declared_sitemaps(raw,'https://example.org'),
                         ['https://example.org/sitemap.xml?page=1'])
    def test_budget_fail_closed(self):
        with self.assertRaisesRegex(e.Hold,'discovery_budget_invalid'):
            p14.research_discover('/tmp/x','/tmp/missing.json','test',max_docs=100)


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        cls.port=cls.server.server_port
        cls.base=f'http://127.0.0.1:{cls.port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.thread.join();cls.server.server_close()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'stage.db'
        self.source_path=Path(self.temp.name)/'source.json'
        self.source=[{'source_id':'fixture_p14','origin':self.base,'allowed_paths':['/events/'],
                     'collection_approved':True,'display_mode':'metadata_only',
                     'rights_basis':'Locally generated fixture domain for bounded sitemap evaluation only.'}]
        self.source_path.write_text(json.dumps(self.source))
        self.target=self.base+'/events/london-new-years-eve-2026'
        Fixture.seen=[]
        self._responses()
    def _responses(self):
        base=self.base
        Fixture.responses={
            '/robots.txt':(200,'text/plain',f'User-agent: PulseSearchBot\nDisallow: /blocked.xml\nSitemap: {base}/index.xml\n'.encode(),{}),
            '/index.xml':(200,'application/xml',sitemap_xml(base+'/sitemap-news.xml',base+'/events-index.xml',kind='sitemapindex'),{}),
            '/events-index.xml':(200,'application/xml',sitemap_xml(base+'/events-2026.xml.gz',kind='sitemapindex'),{}),
            '/sitemap-news.xml':(200,'application/xml',sitemap_xml(base+'/not-approved'),{}),
            '/events-2026.xml.gz':(200,'application/x-gzip',gzip.compress(sitemap_xml(
                base+'/events/london-new-years-eve-2026',base+'/events/new-years-eve-2027',
                base+'/events/event-two','https://evil.example/unknown',base+'/blocked/private')),{}),
            '/events/london-new-years-eve-2026':(200,'text/html',b'<title>should not be fetched in discovery</title>',{}),
        }
    def run_pilot(self,**kw):
        return p14.research_discover(self.db,self.source_path,'What events are happening in London for New Years Eve 2026?',
                          max_docs=6,max_candidates=200,max_depth=2,min_delay=0,allow_local=True,
                          target_url=self.target,**kw)
    def test_london_nested_gzip_stage_only(self):
        result=self.run_pilot()
        self.assertTrue(result['target_discovered'])
        self.assertEqual(result['candidate_urls_staged'],3)
        self.assertEqual(result['pages_crawled'],0)
        self.assertEqual(result['sitemaps_processed'],4)
        self.assertNotIn('/events/london-new-years-eve-2026',Fixture.seen)
        self.assertNotIn('evil.example',' '.join(Fixture.seen))
        with e.dbopen(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM pages').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM sitemap_candidates').fetchone()[0],3)
    def test_respects_sitemap_robots_disallow(self):
        Fixture.responses['/robots.txt']=(200,'text/plain',f'User-agent: PulseSearchBot\nDisallow: /events-index.xml\nSitemap: {self.base}/index.xml\n'.encode(),{})
        result=self.run_pilot()
        self.assertFalse(result['target_discovered'])
        self.assertNotIn('/events-index.xml',Fixture.seen)
    def test_fail_closed_robots_503(self):
        Fixture.responses['/robots.txt']=(503,'text/plain',b'Unavailable',{})
        with self.assertRaisesRegex(e.Hold,'robots_http_503'):self.run_pilot()
        self.assertNotIn('/index.xml',Fixture.seen)
    def test_outside_declared_sitemap_not_visited(self):
        Fixture.responses['/robots.txt']=(200,'text/plain',f'Sitemap: https://outsider.example/x.xml\nSitemap: {self.base}/events-index.xml\n'.encode(),{})
        result=self.run_pilot()
        self.assertEqual(result['sitemaps_declared'],1)
        self.assertNotIn('/index.xml',Fixture.seen)
    def test_paged_child_sitemaps_indexed(self):
        base=self.base
        from xml.sax.saxutils import escape
        children=[base+'/sitemap.xml?type=default&page=0',base+'/sitemap.xml?type=default&page=1']
        Fixture.responses['/index.xml']=(200,'application/xml',sitemap_xml(*(escape(x) for x in children),kind='sitemapindex'),{})
        Fixture.responses['/sitemap.xml?type=default&page=0']=(200,'application/xml',sitemap_xml(base+'/events/other'),{})
        Fixture.responses['/sitemap.xml?type=default&page=1']=(200,'application/xml',sitemap_xml(self.target),{})
        r=self.run_pilot()
        self.assertTrue(r['target_discovered'])
        self.assertEqual(r['child_sitemap_links_seen'],2)
        self.assertEqual(r['child_sitemaps_accepted'],2)
        self.assertEqual(r['child_sitemap_rejections'],{})
        self.assertIn('/sitemap.xml?type=default&page=1', Fixture.seen)
        self.assertNotIn('/events/london-new-years-eve-2026',Fixture.seen)
    def test_child_sitemap_rejection_explained(self):
        base=self.base
        Fixture.responses['/index.xml']=(200,'application/xml',sitemap_xml(base+'/sitemap.xml?key=abc',kind='sitemapindex'),{})
        r=self.run_pilot()
        self.assertFalse(r['target_discovered'])
        self.assertEqual(r['child_sitemap_rejections'],{'unapproved_query':1})
        self.assertEqual(r['sitemap_docs_attempted'],1)
        self.assertNotIn('/sitemap.xml?key=abc',Fixture.seen)
    def test_cyclic_index_bounded(self):
        Fixture.responses['/events-index.xml']=(200,'application/xml',sitemap_xml(self.base+'/index.xml',kind='sitemapindex'),{})
        result=self.run_pilot()
        self.assertLessEqual(result['sitemaps_processed'],3)
        self.assertFalse(result['target_discovered'])
    def test_budget_no_sitemap_visit_after_limit(self):
        r=p14.research_discover(self.db,self.source_path,'events',max_docs=1,max_candidates=200,max_depth=2,
                                 min_delay=0,allow_local=True,target_url=self.target)
        self.assertEqual(r['sitemaps_processed'],1)
        self.assertEqual(Fixture.seen.count('/index.xml'),1)
        self.assertEqual(len(Fixture.seen),2)
    def test_target_out_of_scope_before_network(self):
        with self.assertRaisesRegex(e.Hold,'target_outside_approved_source'):
            p14.research_discover(self.db,self.source_path,'events',allow_local=True,target_url=self.base+'/private')
        self.assertFalse(Fixture.seen)
    def test_fallback_robots_404(self):
        Fixture.responses['/robots.txt']=(404,'text/plain',b'none',{})
        Fixture.responses['/sitemap.xml']=(200,'application/xml',sitemap_xml(self.target),{})
        r=self.run_pilot()
        self.assertTrue(r['used_standard_fallback'])
        self.assertTrue(r['target_discovered'])
    def test_one_explicit_target_index_only(self):
        Fixture.responses['/events/london-new-years-eve-2026']=(200,'text/html',
          b'<html><title>London New Years Eve 2026 official events</title><body>Official London New Years Eve 2026 celebration</body></html>',{})
        result=self.run_pilot(index_discovered_target=True)
        self.assertTrue(result['target_indexed'])
        self.assertEqual(result['target_crawl']['processed_pages'],1)
        self.assertTrue(result['search_results'])
        with e.dbopen(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0],1)
    def test_many_urls_target_late_retained(self):
        urls=[self.base+'/events/old-guidelines-'+str(i) for i in range(450)]+[self.target]
        Fixture.responses['/events-2026.xml.gz']=(200,'application/x-gzip',gzip.compress(sitemap_xml(*urls)),{})
        result=p14.research_discover(self.db,self.source_path,'London New Years Eve 2026',
           max_docs=6,max_candidates=20,max_depth=2,min_delay=0,allow_local=True,target_url=self.target)
        self.assertTrue(result['target_discovered'])
        self.assertEqual(result['candidate_urls_staged'],20)
    def test_failed_sitemap_attempt_budget(self):
        links=[self.base+'/events-'+str(i)+'.xml' for i in range(20)]
        Fixture.responses['/index.xml']=(200,'application/xml',sitemap_xml(*links,kind='sitemapindex'),{})
        result=p14.research_discover(self.db,self.source_path,'events',max_docs=2,
           min_delay=0,allow_local=True)
        self.assertEqual(result['sitemap_docs_attempted'],2)
        self.assertEqual(result['sitemaps_failed'],1)
        self.assertEqual(len(Fixture.seen),3)

    def test_no_declared_cross_site_dns_resolution(self):
        # If external URLs reached the fetch layer, DNS would fail or error; this passes offline.
        r=self.run_pilot()
        self.assertEqual(r['paid_search_api_calls'],0)
        self.assertEqual(r['external_search_engine_calls'],0)

if __name__=='__main__':unittest.main()
