#!/usr/bin/env python3
"""Pulse Search R2-P1: self-hosted, independent, scope-limited web crawler + search API.

Python stdlib only; no search provider/API calls. Local loopback test mode deliberately
separate from live mode. An allowlisted origin is a collection boundary, not a grant
of copyright or database rights. Commercial display is not enabled by this build.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import ssl
import sys
import time
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, parse_qs, unquote
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

VERSION = '0.6.0-r2p4-growth'
UA = 'PulseSearchBot/0.3 (+https://pulseunity.com/)'
MAX_BYTES = 1_000_000
MAX_ROBOTS = 512_000
MAX_LINKS = 80
MAX_SITEMAP_URLS = 150
MAX_DEPTH = 2
MAX_PAGES = 30
TIMEOUT = 10
MIN_DELAY = 1.5
SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sources(
 source_id TEXT PRIMARY KEY, origin TEXT NOT NULL UNIQUE,
 paths TEXT NOT NULL, approved INTEGER NOT NULL CHECK(approved IN (0,1)),
 display_mode TEXT NOT NULL CHECK(display_mode IN ('metadata_only','licensed_snippet')),
 rights_basis TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS frontier(
 url TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 depth INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
 last_error TEXT, parent_url TEXT, last_seen TEXT);
CREATE INDEX IF NOT EXISTS idx_frontier_queue ON frontier(state,depth,url);
CREATE TABLE IF NOT EXISTS pages(
 id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, source_id TEXT NOT NULL REFERENCES sources(source_id),
 title TEXT NOT NULL, body TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 fetched_at TEXT NOT NULL, duplicate_of TEXT, indexed INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS idx_pages_sha ON pages(content_sha256);
CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5(title,body);
CREATE TABLE IF NOT EXISTS fetch_validators(
 url TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 etag TEXT, last_modified TEXT, checked_at TEXT NOT NULL, status INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_fetch_val_source ON fetch_validators(source_id);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY, url TEXT, outcome TEXT NOT NULL, detail TEXT, at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS external_candidates(
 origin TEXT NOT NULL, referrer_source_id TEXT NOT NULL REFERENCES sources(source_id),
 example_url TEXT NOT NULL, referrer_url TEXT NOT NULL, first_seen TEXT NOT NULL,
 last_seen TEXT NOT NULL, sightings INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(origin,referrer_source_id));
CREATE INDEX IF NOT EXISTS idx_external_candidates_source ON external_candidates(referrer_source_id);
'''

class Hold(Exception): pass

def utc(): return datetime.now(timezone.utc).isoformat()

def origin(url):
    p=urlsplit(url)
    return f'{p.scheme}://{p.hostname.lower()}'+(f':{p.port}' if p.port else '')

def normal_url(url, allow_local=False):
    if not isinstance(url,str) or len(url)>1500 or any(ord(c)<32 for c in url): raise Hold('bad_url')
    try: p=urlsplit(url)
    except ValueError: raise Hold('bad_url')
    if p.scheme not in ('https','http') or not p.hostname or p.username is not None or p.password is not None:
        raise Hold('bad_url')
    try: port=p.port
    except ValueError: raise Hold('bad_port')
    if port not in (None,80,443) and not (allow_local and p.hostname in ('localhost','127.0.0.1','::1')):
        raise Hold('nonstandard_port')
    if p.scheme!='https' and not (allow_local and p.hostname in ('localhost','127.0.0.1','::1')):
        raise Hold('https_required')
    if p.hostname.endswith('.') or '%' in p.hostname or p.hostname.endswith('.local'):
        raise Hold('invalid_host')
    if len(parse_qsl(p.query,keep_blank_values=True))>5 or len(p.query)>300: raise Hold('query_trap')
    if re.search(r'\.(?:zip|exe|jpg|jpeg|png|gif|webp|mp4|mp3|svg|woff2?|pdf)(?:$|/)',p.path,re.I):
        raise Hold('non_html_resource')
    path=p.path or '/'
    if any(segment in ('.','..') for segment in unquote(path).split('/')): raise Hold('dot_segment')
    hostname=p.hostname.lower()
    if ':' in hostname: hostname=f'[{hostname}]'
    netloc=hostname+(f':{port}' if port else '')
    return urlunsplit((p.scheme,netloc,path,p.query,''))

def addresses(host,port, allow_local=False):
    try: records=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    except OSError: raise Hold('dns_failure')
    if not records: raise Hold('dns_empty')
    ips=[]
    for r in records:
        raw=r[4][0]
        address=ipaddress.ip_address(raw)
        if not address.is_global and not (allow_local and address.is_loopback):
            raise Hold('private_or_reserved_dns')
        if raw not in ips: ips.append(raw)
    return ips

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, ip, **kw):
        super().__init__(host,port=port,context=ssl.create_default_context(),**kw); self.ip=ip
    def connect(self):
        sock=socket.create_connection((self.ip,self.port),self.timeout)
        self.sock=self._context.wrap_socket(sock,server_hostname=self.host)

class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, port, ip, **kw):
        super().__init__(host,port=port,**kw); self.ip=ip
    def connect(self): self.sock=socket.create_connection((self.ip,self.port),self.timeout)

class Fetcher:
    def __init__(self,allow_local=False):
        self.allow_local=allow_local; self.requests=0; self.last_request={}; self.delays={}
    def get(self,url,limit=MAX_BYTES,headers=None):
        url=normal_url(url,self.allow_local)
        p=urlsplit(url); port=p.port or (443 if p.scheme=='https' else 80)
        key=origin(url)
        if key in self.last_request:
            remaining=self.delays.get(key,0)-(time.monotonic()-self.last_request[key])
            if remaining>0:time.sleep(remaining)
        ip=addresses(p.hostname,port,self.allow_local)[0]
        cls= PinnedHTTPS if p.scheme=='https' else PinnedHTTP
        c=cls(p.hostname,port,ip,timeout=TIMEOUT)
        path=p.path+('?' + p.query if p.query else '')
        hdr={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml,application/xml,text/plain;q=0.8',
             'Accept-Encoding':'identity','Connection':'close','Host':p.netloc}
        if headers: hdr.update(headers)
        try:
            c.request('GET',path,headers=hdr)
            self.last_request[key]=time.monotonic()
            self.requests+=1
            r=c.getresponse(); status=r.status
            mime=r.getheader('Content-Type','').split(';')[0].lower().strip()
            hdrs={k.lower():v for k,v in r.getheaders()}
            if int(r.getheader('Content-Length','0') or '0')>limit: raise Hold('oversize_content_length')
            body=r.read(limit+1)
            if len(body)>limit: raise Hold('oversize_body')
            return status,mime,hdrs,body
        except (socket.timeout,OSError,ssl.SSLError,http.client.HTTPException) as e:
            raise Hold('http_network_error:'+type(e).__name__) from e
        finally: c.close()

class HTMLExtract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts=[]; self.h1_parts=[]; self.text=[]; self.links=[]
        self.skip=0; self.in_title=0; self.in_h1=0; self.noindex=False; self.nofollow=False; self.canonical=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript','svg','template'):
            self.skip+=1
            return
        if tag=='title': self.in_title+=1
        if tag=='h1': self.in_h1+=1
        if tag=='meta' and (a.get('name','').lower() in ('robots','pulsesearchbot')):
            rules=a.get('content','').lower()
            if 'noindex' in rules or 'none' in rules: self.noindex=True
            if 'nofollow' in rules or 'none' in rules: self.nofollow=True
        if tag=='link' and 'canonical' in a.get('rel','').lower().split(): self.canonical=a.get('href')
        if tag=='a' and a.get('href') and 'nofollow' not in a.get('rel','').lower().split():
            self.links.append(a['href'])
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg','template'): self.skip=max(0,self.skip-1)
        if tag=='title': self.in_title=max(0,self.in_title-1)
        if tag=='h1': self.in_h1=max(0,self.in_h1-1)
    def handle_data(self,data):
        if self.skip:return
        s=' '.join(data.split())
        if not s: return
        if self.in_title:self.title_parts.append(s)
        if self.in_h1:self.h1_parts.append(s)
        self.text.append(s)

def parse_html(raw):
    p=HTMLExtract();p.feed(raw.decode('utf-8','replace'))
    title=' '.join(p.title_parts or p.h1_parts).strip()[:300]
    body=' '.join(p.text)[:120000]
    return p,title,body

@contextmanager
def dbopen(path):
    conn=sqlite3.connect(path,timeout=12)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=12000')
    try: yield conn;conn.commit()
    except BaseException: conn.rollback();raise
    finally:conn.close()

def initdb(path):
    p=Path(path).expanduser().resolve();p.parent.mkdir(parents=True,exist_ok=True)
    with dbopen(p) as c:
        c.executescript(SCHEMA)
        c.execute('PRAGMA journal_mode=WAL')
    return p

def validate_sources(items, allow_local=False):
    if not isinstance(items,list) or not 1<=len(items)<=15: raise Hold('source_count')
    seen=set();out=[]
    for s in items:
        if not isinstance(s,dict):raise Hold('bad_source')
        sid=s.get('source_id')
        if not isinstance(sid,str) or not re.fullmatch(r'[a-z0-9_-]{2,60}',sid) or sid in seen:
            raise Hold('bad_or_duplicate_source_id')
        seen.add(sid)
        u=normal_url(s.get('origin',''),allow_local)
        if urlsplit(u).path!='/' or urlsplit(u).query: raise Hold('origin_must_be_root')
        paths=s.get('allowed_paths',[])
        if not isinstance(paths,list) or not paths or not all(isinstance(x,str) and x.startswith('/') and '..' not in x and len(x)<120 for x in paths):raise Hold('bad_paths')
        if s.get('collection_approved') is not True: raise Hold('source_not_approved_for_pilot')
        mode=s.get('display_mode')
        if mode not in ('metadata_only','licensed_snippet'): raise Hold('bad_display_mode')
        basis=s.get('rights_basis')
        if not isinstance(basis,str) or len(basis.strip())<20:raise Hold('missing_rights_basis')
        if mode=='licensed_snippet' and s.get('description_license_confirmed') is not True:
            raise Hold('snippet_license_not_confirmed')
        out.append((sid,origin(u),json.dumps(paths),1,mode,basis.strip(),1))
    if len({s[1] for s in out})!=len(out):raise Hold('duplicate_origin')
    return out

def register_sources(conn,items,allow_local=False):
    records=validate_sources(items,allow_local)
    for s in records:
        old=conn.execute('SELECT * FROM sources WHERE source_id=?',(s[0],)).fetchone()
        if old and not old['enabled']:raise Hold('retired_source_cannot_auto_reactivate')
        if old and (old['origin']!=s[1] or old['paths']!=s[2] or old['display_mode']!=s[4]):
            raise Hold('source_configuration_changed; retire source explicitly first')
        conn.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET approved=excluded.approved,rights_basis=excluded.rights_basis,enabled=1',s)
    return len(records)

def scope(url, source, allow_local=False):
    try: u=normal_url(url,allow_local)
    except Hold:return False
    return origin(u)==source['origin'] and any((p=='/' or urlsplit(u).path==p or urlsplit(u).path.startswith(p.rstrip('/')+'/')) for p in json.loads(source['paths']))

def enqueue(conn,url,source,depth,parent=None,allow_local=False):
    if not scope(url,source,allow_local):return False
    if depth>MAX_DEPTH:return False
    normalized=normal_url(url,allow_local)
    res=conn.execute("INSERT OR IGNORE INTO frontier(url,source_id,depth,state,parent_url) VALUES(?,?,?,'queued',?)",
                     (normalized,source['source_id'],depth,parent))
    return res.rowcount>0

def record_external_candidates(conn, base_url, src, hrefs, allow_local=False, cap=12):
    # Stage external HTTPS origins for manual review. Never crawl, resolve DNS or approve them.
    saved=0; seen=set()
    for href in hrefs[:MAX_LINKS]:
        if saved>=cap:break
        try:
            target=normal_url(urljoin(base_url,href),allow_local=False)
            parsed=urlsplit(target)
            host=parsed.hostname or ''
            if parsed.scheme!='https' or origin(target)==src['origin']:continue
            if parsed.port or not host or host=='localhost' or host.endswith(('.invalid','.test','.example')):continue
            try:
                ipaddress.ip_address(host)
                continue
            except ValueError:pass
            if len(host)>180 or '.' not in host:continue
            org=origin(target)
            if org in seen:continue
            seen.add(org)
            # Strip query strings to avoid tracking and token storage.
            safe_url=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))
            now=utc()
            conn.execute('INSERT INTO external_candidates '
                 '(origin,referrer_source_id,example_url,referrer_url,first_seen,last_seen,sightings) '
                 'VALUES(?,?,?,?,?,?,1) ON CONFLICT(origin,referrer_source_id) DO UPDATE '
                 'SET last_seen=excluded.last_seen,sightings=sightings+1',
                 (org,src['source_id'],safe_url,base_url,now,now))
            saved+=1
        except (Hold,ValueError):continue
    return saved

def log(conn,url,outcome,detail=''):
    conn.execute('INSERT INTO audit(url,outcome,detail,at_utc) VALUES(?,?,?,?)',(url,outcome,str(detail)[:300],utc()))

def robots_text_rules(raw):
    rp=RobotFileParser();rp.parse(raw.decode('utf-8','replace').splitlines())
    return rp

def sitemap_links(raw, base, limit=MAX_SITEMAP_URLS):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise Hold('unsafe_xml')
    try: root=ET.fromstring(raw)
    except ET.ParseError:raise Hold('invalid_sitemap_xml')
    if root.tag.rsplit('}',1)[-1]!='urlset': raise Hold('not_urlset')
    urls=[]
    for e in root.iter():
        if e.tag.rsplit('}',1)[-1]=='loc' and e.text and len(urls)<limit:
            urls.append(e.text.strip())
    return urls

def is_robots_noindex(headers,ex):
    directive=headers.get('x-robots-tag','').lower()
    return ex.noindex or 'noindex' in directive or 'none' in directive

def robots_allowed(fetcher,src,cache,last_call,min_delay):
    key=src['origin']
    if key in cache:return cache[key]
    robots_url=key+'/robots.txt'
    try: status,mime,headers,body=fetcher.get(robots_url,MAX_ROBOTS)
    except Hold as e:
        raise Hold('robots_unreachable:'+str(e))
    last_call[key]=time.monotonic()
    if status==404 or status==410:
        # RFC 9309: a missing robots file is unavailable; allow limited crawling.
        rp=RobotFileParser();rp.parse([])
        cache[key]=(None,min_delay)
    elif status==200:
        if mime not in ('text/plain','text/html',''):raise Hold('robots_bad_mime')
        rp=robots_text_rules(body)
        cd=rp.crawl_delay('PulseSearchBot') or rp.crawl_delay('*') or 0
        cache[key]=(rp,max(min_delay,float(cd)))
    else:
        raise Hold('robots_http_'+str(status))
    fetcher.delays[key]=cache[key][1]
    return cache[key]

def tick(origin_key,last_call,delay):
    if origin_key in last_call:
        rest=delay-(time.monotonic()-last_call[origin_key])
        if rest>0:time.sleep(rest)

def fetch_scope(fetcher,url,src,limit=MAX_BYTES, allow_local=False, robots=None,request_headers=None):
    visited=set(); current=url
    for _ in range(4):
        if not scope(current,src,allow_local):raise Hold('redirect_out_of_scope')
        if robots is not None and not robots.can_fetch(UA,current):raise Hold('redirect_robots_disallow')
        status,mime,headers,raw=fetcher.get(current,limit,headers=request_headers if current==url else None)
        if status in (301,302,303,307,308):
            next_url=urljoin(current,headers.get('location',''))
            if next_url==current or next_url in visited:raise Hold('redirect_loop')
            visited.add(current);current=next_url;continue
        return current,status,mime,headers,raw
    raise Hold('redirect_limit')

def promote_dependents(conn, old_url):
    matches=conn.execute('SELECT id,url,title,body FROM pages WHERE duplicate_of=? ORDER BY id',(old_url,)).fetchall()
    if not matches:return
    winner=matches[0]
    conn.execute('UPDATE pages SET duplicate_of=NULL,indexed=1 WHERE id=?',(winner['id'],))
    conn.execute('INSERT INTO page_fts(rowid,title,body) VALUES(?,?,?)',
                 (winner['id'],winner['title'],winner['body']))
    for row in matches[1:]:
        conn.execute('UPDATE pages SET duplicate_of=? WHERE id=?',(winner['url'],row['id']))

def purge_page(conn,url):
    old=conn.execute('SELECT id FROM pages WHERE url=?',(url,)).fetchone()
    if old:
        conn.execute('DELETE FROM page_fts WHERE rowid=?',(old['id'],))
        conn.execute('DELETE FROM pages WHERE id=?',(old['id'],))
        promote_dependents(conn,url)
    conn.execute('DELETE FROM fetch_validators WHERE url=?',(url,))
    return bool(old)

def record_validator(conn, url, source, headers, status):
    # Only store bounded, line-safe HTTP validator fields.
    def safe(name):
        v=headers.get(name,'')
        return v if isinstance(v,str) and len(v)<=250 and '\r' not in v and '\n' not in v else None
    current=conn.execute('SELECT etag,last_modified FROM fetch_validators WHERE url=?',(url,)).fetchone()
    etag=safe('etag') or ((current['etag'] if current else None) if status==304 else None)
    modified=safe('last-modified') or ((current['last_modified'] if current else None) if status==304 else None)
    conn.execute('''INSERT INTO fetch_validators(url,source_id,etag,last_modified,checked_at,status)
       VALUES(?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET
       etag=excluded.etag,last_modified=excluded.last_modified,
       checked_at=excluded.checked_at,status=excluded.status''',
       (url,source['source_id'],etag,modified,utc(),status))

def conditional_headers(conn,url):
    row=conn.execute('''SELECT v.etag,v.last_modified FROM fetch_validators v
       JOIN pages p ON p.url=v.url WHERE v.url=? AND p.indexed=1''',(url,)).fetchone()
    if not row:return {}
    return {key:row[col] for key,col in (('If-None-Match','etag'),('If-Modified-Since','last_modified')) if row[col]}

def reschedule(db, min_age_hours=24.0, limit=100):
    # Explicit operator action. A completed URL is never recrawled accidentally.
    if not 0<=min_age_hours<=8760 or not 1<=limit<=1000:raise Hold('revisit_budget_invalid')
    threshold=(datetime.now(timezone.utc)-timedelta(hours=min_age_hours)).isoformat()
    with dbopen(db) as c:
        ids=[r['url'] for r in c.execute('''SELECT f.url FROM frontier f
            JOIN sources s ON f.source_id=s.source_id
            WHERE f.state='done' AND f.last_seen<=? AND s.approved=1 AND s.enabled=1
            ORDER BY f.last_seen ASC,f.url ASC LIMIT ?''',(threshold,limit))]
        for url in ids:
            c.execute("UPDATE frontier SET state='queued',last_error=NULL WHERE url=? AND state='done'",(url,))
        log(c,'scheduler','revisit_enqueued',str(len(ids)))
    return {'queued_for_revisit':len(ids),'min_age_hours':min_age_hours,'limit':limit}

def index_page(conn,url,source,title,body,raw_hash,allow_index):
    if not allow_index:
        purge_page(conn,url)
        return 'not_indexed'
    if not title or len(body)<30:return 'empty_content'
    other=conn.execute('SELECT url FROM pages WHERE content_sha256=? AND indexed=1 AND url<>? LIMIT 1',(raw_hash,url)).fetchone()
    duplicate=other['url'] if other else None
    old=conn.execute('SELECT id FROM pages WHERE url=?',(url,)).fetchone()
    if old:
        previous=conn.execute('SELECT content_sha256,duplicate_of,title,body FROM pages WHERE id=?',(old['id'],)).fetchone()
        if previous['content_sha256']==raw_hash and previous['duplicate_of']==duplicate and previous['title']==title and previous['body']==body:
            conn.execute('UPDATE pages SET fetched_at=? WHERE id=?',(utc(),old['id']))
            return 'unchanged_content'
        conn.execute('DELETE FROM page_fts WHERE rowid=?',(old['id'],))
        if previous['content_sha256']!=raw_hash and previous['duplicate_of'] is None:
            promote_dependents(conn,url)
        conn.execute('UPDATE pages SET title=?,body=?,content_sha256=?,fetched_at=?,duplicate_of=?,indexed=? WHERE id=?',
                     (title,body,raw_hash,utc(),duplicate,int(duplicate is None),old['id']))
        rowid=old['id']
    else:
        rowid=conn.execute('INSERT INTO pages(url,source_id,title,body,content_sha256,fetched_at,duplicate_of,indexed) VALUES(?,?,?,?,?,?,?,?)',
                           (url,source['source_id'],title,body,raw_hash,utc(),duplicate,int(duplicate is None))).lastrowid
    if duplicate is None:conn.execute('INSERT INTO page_fts(rowid,title,body) VALUES(?,?,?)',(rowid,title,body))
    return 'duplicate' if duplicate else 'indexed'

def crawl(db,sources_path,seeds,max_pages=8,max_depth=1,min_delay=MIN_DELAY,allow_local=False,sitemaps=False,scheduled_urls=None):
    if not 1<=max_pages<=MAX_PAGES or not 0<=max_depth<=MAX_DEPTH: raise Hold('crawl_budget_invalid')
    if not (0<=min_delay<=30):raise Hold('min_delay_invalid')
    if min_delay<1 and not allow_local: raise Hold('live_min_delay_below_one_second')
    entries=json.loads(Path(sources_path).read_text(encoding='utf-8'))
    if not seeds and not sitemaps and scheduled_urls is None:raise Hold('no_seeds')
    if scheduled_urls is not None and (not scheduled_urls or len(scheduled_urls)>MAX_PAGES or len(set(scheduled_urls))!=len(scheduled_urls)):
        raise Hold('bad_selected_crawl_urls')
    f=Fetcher(allow_local)
    report={'version':VERSION,'mode':'local_fixture' if allow_local else 'live_public_internet',
            'started_at':utc(),'requested_page_budget':max_pages,'outcomes':{},'fetch_requests':0,
            'paid_search_api_requests':0,'searched_external_engine':False}
    with dbopen(db) as conn:
        register_sources(conn,entries,allow_local)
        sources={s['source_id']:s for s in conn.execute('SELECT * FROM sources WHERE enabled=1')}
        for url in seeds:
            candidate=[s for s in sources.values() if scope(url,s,allow_local)]
            if len(candidate)!=1:raise Hold('seed_out_of_approved_scope:'+url[:100])
            enqueue(conn,url,candidate[0],0,allow_local=allow_local)
        cache={};last={};sitemap_done=set();processed=0
        while processed<max_pages:
            if scheduled_urls is None:
                item=conn.execute("SELECT * FROM frontier WHERE state='queued' AND depth<=? ORDER BY depth,url LIMIT 1",(max_depth,)).fetchone()
            else:
                marks=','.join('?' for _ in scheduled_urls)
                item=conn.execute("SELECT * FROM frontier WHERE state='queued' AND depth<=? AND url IN ("+marks+") ORDER BY depth,url LIMIT 1",(max_depth,*scheduled_urls)).fetchone()
            if item is None:break
            src=sources[item['source_id']];url=item['url'];processed+=1
            try:
                rp,delay=robots_allowed(f,src,cache,last,min_delay)
                if rp is not None and not rp.can_fetch(UA,url):raise Hold('robots_disallow')
                if sitemaps and src['source_id'] not in sitemap_done:
                    sitemap_done.add(src['source_id'])
                    site=src['origin']+'/sitemap.xml'
                    if rp is None or rp.can_fetch(UA,site):
                        try:
                            scurl,status,mime,headers,data=fetch_scope(f,site,src,limit=MAX_BYTES,allow_local=allow_local,robots=rp)
                            last[src['origin']]=time.monotonic()
                            if status==200 and mime in ('application/xml','text/xml','application/rss+xml',''):
                                for link in sitemap_links(data,scurl):enqueue(conn,link,src,1,allow_local=allow_local)
                        except Hold: pass  # Sitemap is optional; normal crawl continues.
                final_url,status,mime,headers,raw=fetch_scope(f,url,src,allow_local=allow_local,robots=rp,
                    request_headers=conditional_headers(conn,url))
                last[src['origin']]=time.monotonic()
                if final_url!=url and rp is not None and not rp.can_fetch(UA,final_url):raise Hold('redirect_robots_disallow')
                if status==304:
                    if 'noindex' in headers.get('x-robots-tag','').lower():
                        purge_page(conn,final_url)
                        conn.execute("UPDATE frontier SET state='done',last_error=NULL,last_seen=? WHERE url=?",(utc(),url))
                        log(conn,url,'not_indexed_304')
                        outcome='not_indexed_304'
                        report['outcomes'][outcome]=report['outcomes'].get(outcome,0)+1
                        continue
                    prior=conn.execute('SELECT id FROM pages WHERE url=? AND source_id=? AND indexed=1',
                        (final_url,src['source_id'])).fetchone()
                    if not prior:raise Hold('unexpected_304_without_indexed_page')
                    record_validator(conn,final_url,src,headers,status)
                    conn.execute("UPDATE frontier SET state='done',last_error=NULL,last_seen=? WHERE url=?",(utc(),url))
                    log(conn,url,'not_modified_304')
                    outcome='not_modified_304'
                    report['outcomes'][outcome]=report['outcomes'].get(outcome,0)+1
                    continue
                if status in (403,404,410,451):
                    purge_page(conn,url)
                    conn.execute("UPDATE frontier SET state='blocked',last_error=?,last_seen=? WHERE url=?",('page_http_'+str(status),utc(),url))
                    log(conn,url,'removed_or_denied',str(status))
                    outcome='removed_or_denied_'+str(status)
                    report['outcomes'][outcome]=report['outcomes'].get(outcome,0)+1
                    continue
                if status!=200:raise Hold('page_http_'+str(status))
                if mime not in ('text/html','application/xhtml+xml'):raise Hold('not_html')
                parser,title,body=parse_html(raw)
                canonical=parser.canonical
                canonical_valid=True
                if canonical:
                    canonical_abs=urljoin(final_url,canonical)
                    if not scope(canonical_abs,src,allow_local) or normal_url(canonical_abs,allow_local)!=final_url:
                        canonical_valid=False
                noindex=is_robots_noindex(headers,parser) or not canonical_valid
                text_hash=hashlib.sha256((title+'\n'+body).encode()).hexdigest()
                outcome=index_page(conn,final_url,src,title,body,text_hash,not noindex)
                if outcome!='not_indexed':record_validator(conn,final_url,src,headers,200)
                if not parser.nofollow and 'nofollow' not in headers.get('x-robots-tag','').lower():
                    record_external_candidates(conn,final_url,src,parser.links,allow_local)
                    for href in parser.links[:MAX_LINKS]:
                        try: next_url=normal_url(urljoin(final_url,href),allow_local)
                        except Hold:continue
                        enqueue(conn,next_url,src,item['depth']+1,final_url,allow_local)
                conn.execute("UPDATE frontier SET state='done',last_error=NULL,last_seen=? WHERE url=?",(utc(),url))
                log(conn,url,outcome)
            except Hold as e:
                # A newly disallowed URL must not remain indexed after the robots check.
                if str(e) in ('robots_disallow','redirect_robots_disallow'):
                    purge_page(conn,url)
                outcome='hold:'+str(e)
                conn.execute("UPDATE frontier SET state='blocked',last_error=?,last_seen=? WHERE url=?",(str(e)[:200],utc(),url))
                log(conn,url,'hold',str(e))
            report['outcomes'][outcome]=report['outcomes'].get(outcome,0)+1
        report['processed_pages']=processed
        report['index_pages']=conn.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
        report['remaining_queue']=conn.execute("SELECT COUNT(*) FROM frontier WHERE state='queued'").fetchone()[0]
    report['fetch_requests']=f.requests
    report['effective_origin_delays']=dict(f.delays)
    report['finished_at']=utc()
    return report

def search(conn,q,limit=10,offset=0):
    if not isinstance(q,str) or len(q)>160 or not q.strip():raise Hold('bad_query')
    tokens=re.findall(r'[^\W_]+',q,flags=re.UNICODE)[:12]
    if not tokens:return []
    match=' OR '.join('"'+t.replace('"','')+'"' for t in tokens)
    # FTS-only corpus: no paid search provider called here; source revocation checked at query time.
    sql='''SELECT p.url,p.title,p.body,p.fetched_at,p.source_id,s.display_mode,
       bm25(page_fts,6.0,1.0) AS rank FROM page_fts
       JOIN pages p ON p.id=page_fts.rowid
       JOIN sources s ON s.source_id=p.source_id
       WHERE page_fts MATCH ? AND p.indexed=1 AND s.enabled=1 AND s.approved=1
       ORDER BY rank ASC,p.url ASC LIMIT ? OFFSET ?'''
    rows=conn.execute(sql,(match,limit,offset)).fetchall()
    return [{'url':r['url'],'title':r['title'],'source_id':r['source_id'],
             'fetched_at':r['fetched_at'],'rank':round(float(r['rank']),6),
             **({'snippet':r['body'][:180]} if r['display_mode']=='licensed_snippet' else {})} for r in rows]

def stats(conn):
    return {'version':VERSION,'indexed_pages':conn.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0],
            'queued_urls':conn.execute("SELECT COUNT(*) FROM frontier WHERE state='queued'").fetchone()[0],
            'blocked_urls':conn.execute("SELECT COUNT(*) FROM frontier WHERE state='blocked'").fetchone()[0],
            'revisit_metadata_rows':conn.execute('SELECT COUNT(*) FROM fetch_validators').fetchone()[0],
            'enabled_sources':conn.execute('SELECT COUNT(*) FROM sources WHERE enabled=1').fetchone()[0]}

def retire_source(db,sid):
    with dbopen(db) as c:
        if not c.execute('SELECT 1 FROM sources WHERE source_id=?',(sid,)).fetchone():raise Hold('unknown_source')
        # Fail closed: delete searchable rows and locally stored body text as well as disabling the source.
        removed=[(r['id'],r['url']) for r in c.execute('SELECT id,url FROM pages WHERE source_id=?',(sid,))]
        ids=[a for a,b in removed]; removed_urls=[b for a,b in removed]
        for i in ids:c.execute('DELETE FROM page_fts WHERE rowid=?',(i,))
        c.execute('DELETE FROM pages WHERE source_id=?',(sid,))
        # If a retired source held the canonical copy, promote one retained duplicate.
        for removed_url in removed_urls:
            matches=c.execute('SELECT id,url,title,body FROM pages WHERE duplicate_of=? ORDER BY id',(removed_url,)).fetchall()
            if not matches:continue
            winner=matches[0]
            c.execute('UPDATE pages SET duplicate_of=NULL,indexed=1 WHERE id=?',(winner['id'],))
            c.execute('INSERT INTO page_fts(rowid,title,body) VALUES(?,?,?)',(winner['id'],winner['title'],winner['body']))
            for other in matches[1:]:c.execute('UPDATE pages SET duplicate_of=? WHERE id=?',(winner['url'],other['id']))
        c.execute('DELETE FROM fetch_validators WHERE source_id=?',(sid,))
        c.execute('DELETE FROM frontier WHERE source_id=?',(sid,))
        c.execute('UPDATE sources SET enabled=0,approved=0 WHERE source_id=?',(sid,))
        log(c,'source:'+sid,'retired',f'deleted {len(ids)} stored pages')
    return len(ids)

def make_handler(db,token):
    class API(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.0'
        def log_message(self,fmt,*args): pass
        def do_GET(self):
            # Explicit token gate applies to all endpoints including health/stats.
            auth=self.headers.get('Authorization','')
            if not secrets.compare_digest(auth,'Bearer '+token):
                return self.send_json(401,{'error':'unauthorized'})
            p=urlsplit(self.path)
            try:
                with dbopen(db) as c:
                    if p.path=='/health':return self.send_json(200,{'status':'ok','version':VERSION})
                    if p.path=='/v1/stats':return self.send_json(200,stats(c))
                    if p.path!='/v1/search':return self.send_json(404,{'error':'not_found'})
                    vals=parse_qs(p.query,keep_blank_values=True)
                    if any(len(v)!=1 for v in vals.values()):raise Hold('duplicate_parameters')
                    q=vals.get('q',[''])[0]
                    limit=int(vals.get('limit',['10'])[0]);offset=int(vals.get('offset',['0'])[0])
                    if not 1<=limit<=50 or not 0<=offset<=10000:raise Hold('pagination_out_of_range')
                    hits=search(c,q,limit,offset)
                return self.send_json(200,{'query':q,'results':hits,'count':len(hits),'limit':limit,'offset':offset})
            except (Hold,ValueError,sqlite3.OperationalError) as e:
                return self.send_json(400,{'error':'invalid_request','detail':str(e)[:100]})
        def send_json(self,status,obj):
            raw=json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
    return API

def serve(db,token,port=8765):
    if not token or len(token)<24:raise Hold('PULSE_SEARCH_TOKEN must be at least 24 characters')
    # Bind to private loopback only; production gateway/auth controls are a separate milestone.
    httpd=ThreadingHTTPServer(('127.0.0.1',port),make_handler(db,token))
    print('Pulse Search API bound to 127.0.0.1:'+str(port),flush=True)
    try:httpd.serve_forever(poll_interval=0.2)
    finally:httpd.server_close()

def main(argv=None):
    ap=argparse.ArgumentParser(description='Standalone Pulse Search crawler/index/API')
    sub=ap.add_subparsers(dest='command',required=True)
    cmd=sub.add_parser('init');cmd.add_argument('--db',required=True)
    cmd=sub.add_parser('crawl');cmd.add_argument('--db',required=True);cmd.add_argument('--sources',required=True)
    cmd.add_argument('--seed',action='append',default=[]);cmd.add_argument('--max-pages',type=int,default=8)
    cmd.add_argument('--max-depth',type=int,default=1);cmd.add_argument('--min-delay',type=float,default=MIN_DELAY)
    cmd.add_argument('--sitemaps',action='store_true');cmd.add_argument('--fixture-loopback',action='store_true')
    cmd=sub.add_parser('reschedule');cmd.add_argument('--db',required=True)
    cmd.add_argument('--min-age-hours',type=float,default=24);cmd.add_argument('--limit',type=int,default=100)
    cmd=sub.add_parser('search');cmd.add_argument('--db',required=True);cmd.add_argument('--q',required=True)
    cmd.add_argument('--limit',type=int,default=10)
    cmd=sub.add_parser('stats');cmd.add_argument('--db',required=True)
    cmd=sub.add_parser('retire-source');cmd.add_argument('--db',required=True);cmd.add_argument('--source-id',required=True)
    cmd=sub.add_parser('serve');cmd.add_argument('--db',required=True);cmd.add_argument('--port',type=int,default=8765)
    a=ap.parse_args(argv)
    try:
        if a.command=='init':print(json.dumps({'database':str(initdb(a.db))}))
        elif a.command=='crawl':
            print(json.dumps(crawl(a.db,a.sources,a.seed,a.max_pages,a.max_depth,a.min_delay,a.fixture_loopback,a.sitemaps),indent=2))
        elif a.command=='serve':serve(a.db,os.getenv('PULSE_SEARCH_TOKEN',''),a.port)
        elif a.command=='reschedule':print(json.dumps(reschedule(a.db,a.min_age_hours,a.limit),indent=2))
        elif a.command=='retire-source':print(json.dumps({'removed_pages':retire_source(a.db,a.source_id)}))
        else:
            with dbopen(a.db) as c:
                print(json.dumps(search(c,a.q,a.limit) if a.command=='search' else stats(c),indent=2,ensure_ascii=False))
    except Hold as e:
        print('HOLD: '+str(e),file=sys.stderr);return 2
    return 0

if __name__=='__main__':sys.exit(main())
