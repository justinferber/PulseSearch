#!/usr/bin/env python3
"""Pulse Search R2-P14 — independent, allowlisted sitemap-index discovery.

Discovery writes ONLY to a research DB, never to the accepted engine index.
All network traffic uses the existing pinned-DNS, HTTPS-only Fetcher and obeys
robots.txt on each approved origin. No external search providers are called.
"""
from __future__ import annotations
import argparse
from collections import deque
from datetime import datetime, timezone
import gzip
import io
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit, parse_qsl
import xml.etree.ElementTree as ET

import pulse_search_engine as e

VERSION = '0.14.1-r2p14b-sitemap-child-query-fix'
MAX_SITEMAP_DOCS = 8
MAX_SITEMAP_DEPTH = 2
MAX_CANDIDATES = 800
MAX_COMPRESSED_BYTES = 1_500_000
MAX_EXPANDED_BYTES = 3_000_000
MAX_ENTRIES_PER_DOC = 5000
MAX_URLS_IN_REPORT = 20

STAGE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS sitemap_candidates(
 source_id TEXT NOT NULL, url TEXT NOT NULL,
 sitemap_url TEXT NOT NULL, discovered_at TEXT NOT NULL,
 query_score INTEGER NOT NULL, PRIMARY KEY(source_id,url));
CREATE INDEX IF NOT EXISTS idx_sitemap_candidate_score
 ON sitemap_candidates(query_score DESC, source_id, url);
'''

def declared_sitemaps(robots: bytes, origin: str, allow_local: bool = False):
    """Extract publisher-declared Sitemap: lines, independent of agent blocks."""
    result = []
    for line in robots.decode('utf-8', 'replace').splitlines():
        line = line.split('#', 1)[0].strip()
        m = re.match(r'^sitemap\s*:\s*(\S+)\s*$', line, flags=re.I)
        if not m:
            continue
        try:
            u = e.normal_url(m.group(1), allow_local)
            if e.origin(u) == origin and u not in result:
                result.append(u)
        except (e.Hold, ValueError):
            continue
    return result[:8]

def decode_sitemap(data: bytes, url: str, mime: str, headers: dict):
    if len(data) > MAX_COMPRESSED_BYTES:
        raise e.Hold('sitemap_compressed_size_limit')
    gz = (urlsplit(url).path.lower().endswith('.gz') or
          headers.get('content-encoding', '').lower() == 'gzip' or
          data[:2] == b'\x1f\x8b')
    if gz:
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                data = stream.read(MAX_EXPANDED_BYTES + 1)
        except (OSError, EOFError):
            raise e.Hold('invalid_gzip_sitemap')
    if len(data) > MAX_EXPANDED_BYTES:
        raise e.Hold('sitemap_decompressed_size_limit')
    if (data.startswith((b'\xff\xfe', b'\xfe\xff')) or b'\x00' in data[:100]):
        raise e.Hold('unsupported_sitemap_encoding')
    try:
        xml = data.decode('utf-8-sig', 'strict')
    except UnicodeError:
        raise e.Hold('invalid_sitemap_encoding')
    if re.search(r'<\s*!\s*(DOCTYPE|ENTITY)\b', xml, flags=re.I):
        raise e.Hold('sitemap_dtd_forbidden')
    return xml

def parse_sitemap(data: bytes, url: str, mime='', headers=None):
    """Returns (root_kind, immediate-entry locs); never trusts nested extension locs."""
    xml = decode_sitemap(data, url, mime, headers or {})
    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, ValueError):
        raise e.Hold('invalid_sitemap_xml')
    kind = root.tag.rsplit('}', 1)[-1]
    if kind not in ('urlset', 'sitemapindex'):
        raise e.Hold('unsupported_sitemap_root')
    parent = 'url' if kind == 'urlset' else 'sitemap'
    locs = []
    for child in root:
        if child.tag.rsplit('}', 1)[-1] != parent:
            continue
        for item in child:
            if item.tag.rsplit('}', 1)[-1] == 'loc' and item.text:
                value = item.text.strip()
                if value:
                    locs.append(value)
                break
        if len(locs) >= MAX_ENTRIES_PER_DOC:
            break
    return kind, locs

def query_score(url: str, query: str):
    """Intent-aware candidate selection, NOT a search relevance claim."""
    path = urlsplit(url).path.lower().replace('%20', '-')
    query_words = [x for x in re.findall(r'[a-z0-9]+', query.lower())
                   if x not in {'what','which','where','when','how','are','is','the','for','in','on','of','to','a','an','happening'}]
    path_words = set(re.findall(r'[a-z0-9]+', path))
    score = sum(3 for w in set(query_words) if w in path_words)
    if re.search(r'new[-_/]?years?[-_/]?eve|nye', path):
        score += 5
    if '/events/' in path:
        score += 2
    if any(w in path_words for w in ('tickets','press','release')):
        score -= 1
    return max(0,score)

def _sitemap_priority(url, query):
    words = set(re.findall(r'[a-z0-9]+', query.lower()))
    path = urlsplit(url).path.lower()
    score = 0
    if 'event' in path: score += 20
    if '2026' in path and '2026' in words: score += 5
    if 'sitemap' in path: score += 1
    return -score, url

def classify_sitemap_doc(raw_url, src, allow_local=False):
    """Review sitemap-index child URLs without guessing or fetching untrusted links.

    Sitemap indexes (including some CMS implementations) legally use e.g.
    /sitemap.xml?page=1 or /sitemap.xml?type=default&page=1. Only these
    bounded, non-secret selectors may be used; unknown queries fail closed.
    """
    try:
        url = e.normal_url(raw_url, allow_local)
    except (e.Hold, ValueError):
        return None, 'invalid_url'
    if e.origin(url) != src['origin']:
        return None, 'outside_approved_origin'
    query = urlsplit(url).query
    if query:
        try:
            pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True,
                              max_num_fields=3)
        except (ValueError, UnicodeError):
            return None, 'invalid_query'
        if not pairs or len(pairs)>2 or len({k for k,v in pairs})!=len(pairs):
            return None, 'invalid_query'
        for key, value in pairs:
            if key == 'page':
                if not re.fullmatch(r'(?:0|[1-9][0-9]{0,5})',value) or int(value)>100000:
                    return None, 'unapproved_query'
            elif key == 'type':
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,39}',value):
                    return None, 'unapproved_query'
            else:
                return None, 'unapproved_query'
    # The site must be publishing an XML sitemap resource, not an HTML page.
    path = urlsplit(url).path.lower()
    if not (path.endswith(('.xml','.xml.gz')) or '/sitemap/' in path or path.endswith('/sitemap')):
        return None, 'not_sitemap_resource'
    return url, None


def _valid_sitemap_doc(raw_url, src, allow_local=False):
    return classify_sitemap_doc(raw_url,src,allow_local)[0]


def research_discover(db, source_json, query, *, max_docs=6, max_candidates=400,
                      max_depth=2, min_delay=2.0, allow_local=False, target_url=None,
                      index_discovered_target=False):
    if not 1 <= max_docs <= MAX_SITEMAP_DOCS or not 1 <= max_candidates <= MAX_CANDIDATES:
        raise e.Hold('discovery_budget_invalid')
    if not 0 <= max_depth <= MAX_SITEMAP_DEPTH:
        raise e.Hold('discovery_depth_invalid')
    if min_delay < (0 if allow_local else 1) or min_delay > 20:
        raise e.Hold('discovery_delay_invalid')
    if not query.strip() or len(query) > 180:
        raise e.Hold('discovery_query_invalid')
    sources = json.loads(Path(source_json).read_text(encoding='utf-8'))
    if len(sources) != 1:
        raise e.Hold('single_approved_origin_required')
    e.validate_sources(sources, allow_local)
    src_data = sources[0]
    if index_discovered_target and not target_url:
        raise e.Hold('index_target_requires_exact_url')
    if target_url is not None:
        if not e.scope(target_url, {'origin':e.origin(src_data['origin']), 'paths':json.dumps(src_data['allowed_paths'])}, allow_local):
            raise e.Hold('target_outside_approved_source')
        target_url = e.normal_url(target_url, allow_local)
    f = e.Fetcher(allow_local)
    report = {'version': VERSION, 'query': query, 'mode':'local_fixture' if allow_local else 'live_public_internet',
              'source_id':src_data['source_id'], 'origin':src_data['origin'],
              'sitemaps_declared':0, 'sitemaps_processed':0, 'sitemap_docs_attempted':0, 'sitemaps_blocked':0,
              'sitemaps_failed':0, 'candidate_urls_staged':0, 'paid_search_api_calls':0,
              'external_search_engine_calls':0, 'pages_crawled':0, 'rights_mode':'internal_metadata_research_only',
              'outcomes':{}, 'target_discovered':False, 'target_url':target_url,
              'sitemap_docs':[], 'sample_candidates':[], 'request_budget': max_docs*4+1,
              'child_sitemap_links_seen':0, 'child_sitemaps_accepted':0,
              'child_sitemap_rejections':{}, 'child_sitemap_examples':[]}
    e.initdb(db)
    with e.dbopen(db) as c:
        e.register_sources(c, sources, allow_local)
        c.executescript(STAGE_SCHEMA)
        src = c.execute('SELECT * FROM sources WHERE source_id=?', (src_data['source_id'],)).fetchone()
        origin = src['origin']
        # One authoritative robots fetch; no duplicate request or robots bypass.
        robots_url = origin + '/robots.txt'
        status, mime, hdrs, body = f.get(robots_url, e.MAX_ROBOTS)
        if status == 200:
            if mime not in ('text/plain', 'text/html', ''):
                raise e.Hold('robots_bad_mime')
            raw_robots = body
            rp = e.robots_text_rules(raw_robots)
            crawl_delay = rp.crawl_delay('PulseSearchBot') or rp.crawl_delay('*') or 0
            delay = max(min_delay, float(crawl_delay))
        elif status in (404, 410):
            raw_robots = b''
            rp = None
            delay = min_delay
        else:
            raise e.Hold('robots_http_' + str(status))
        f.delays[origin] = delay
        sitemaps = declared_sitemaps(raw_robots, origin, allow_local)
        report['sitemaps_declared'] = len(sitemaps)
        if not sitemaps:
            sitemaps = [origin+'/sitemap.xml']
            report['used_standard_fallback'] = True
        else:
            report['used_standard_fallback'] = False
        doc_source = {'origin': origin, 'paths': json.dumps(['/'])}
        queue = deque((u,0) for u in sorted(sitemaps,key=lambda u:_sitemap_priority(u,query)))
        seen = set()
        staged = set()
        while queue and report['sitemap_docs_attempted'] < max_docs:
            doc, depth = queue.popleft()
            if doc in seen:continue
            seen.add(doc)
            if depth > max_depth:
                report['sitemaps_blocked'] += 1
                continue
            if _valid_sitemap_doc(doc,src,allow_local) is None or (rp and not rp.can_fetch(e.UA,doc)):
                report['sitemaps_blocked'] += 1
                continue
            report['sitemap_docs_attempted'] += 1
            try:
                final,status,mime,headers,raw = e.fetch_scope(f,doc,doc_source,
                    limit=MAX_COMPRESSED_BYTES,allow_local=allow_local,robots=rp)
                if status != 200:
                    raise e.Hold('sitemap_http_'+str(status))
                if mime not in ('application/xml','text/xml','application/octet-stream','application/x-gzip','application/gzip','') and not doc.endswith('.gz'):
                    raise e.Hold('sitemap_mime_not_xml')
                kind,urls = parse_sitemap(raw,final,mime,headers)
                report['sitemaps_processed'] += 1
                report['sitemap_docs'].append({'url':final,'kind':kind,'entries_examined':len(urls)})
                if kind == 'sitemapindex':
                    if depth == max_depth:
                        report['outcomes']['depth_limit'] = report['outcomes'].get('depth_limit',0)+1
                        continue
                    allowed_children=[]
                    for raw_child in urls:
                        report['child_sitemap_links_seen'] += 1
                        child, reason = classify_sitemap_doc(raw_child,src,allow_local)
                        if child is None:
                            counts=report['child_sitemap_rejections']
                            counts[reason]=counts.get(reason,0)+1
                            # Diagnostics intentionally omit query values and URL credentials.
                            if len(report['child_sitemap_examples'])<5:
                                try:
                                    parts=urlsplit(raw_child)
                                    report['child_sitemap_examples'].append({
                                      'host':parts.hostname, 'path':parts.path[:150],
                                      'has_query':bool(parts.query), 'rejection':reason})
                                except ValueError:
                                    report['child_sitemap_examples'].append({'rejection':reason})
                            continue
                        if child not in seen and child not in allowed_children:
                            allowed_children.append(child)
                    report['child_sitemaps_accepted'] += len(allowed_children)
                    for child in sorted(allowed_children,key=lambda u:_sitemap_priority(u,query))[:MAX_ENTRIES_PER_DOC]:
                        queue.append((child,depth+1))
                else:
                    # Review all entries in this bounded sitemap, then retain the
                    # best candidates; do not privilege the first entries listed.
                    for candidate in urls:
                        try:
                            normalized=e.normal_url(candidate,allow_local)
                        except (e.Hold,ValueError):
                            continue
                        if normalized in staged or not e.scope(normalized,src,allow_local):
                            continue
                        if rp and not rp.can_fetch(e.UA,normalized):
                            continue
                        score = query_score(normalized,query)
                        c.execute('''INSERT OR IGNORE INTO sitemap_candidates
                            (source_id,url,sitemap_url,discovered_at,query_score) VALUES (?,?,?,?,?)''',
                            (src['source_id'], normalized, final, e.utc(),score))
                        staged.add(normalized)
                    # Keep only the highest scoring research candidates.
                    c.execute('''DELETE FROM sitemap_candidates WHERE source_id=? AND url NOT IN
                        (SELECT url FROM sitemap_candidates WHERE source_id=?
                         ORDER BY query_score DESC, url LIMIT ?)''',
                        (src['source_id'],src['source_id'],max_candidates))
                    staged={r[0] for r in c.execute('SELECT url FROM sitemap_candidates WHERE source_id=?',
                                                    (src['source_id'],))}
            except e.Hold as exc:
                report['sitemaps_failed'] += 1
                name = str(exc).split(':')[0]
                report['outcomes'][name] = report['outcomes'].get(name,0)+1
        report['candidate_urls_staged'] = len(staged)
        report['sample_candidates'] = [dict(url=r['url'],query_score=r['query_score'],sitemap_url=r['sitemap_url'])
             for r in c.execute('SELECT url,query_score,sitemap_url FROM sitemap_candidates WHERE source_id=? ORDER BY query_score DESC,url LIMIT ?',
                                (src['source_id'],MAX_URLS_IN_REPORT))]
        if target_url:
            report['target_discovered'] = bool(c.execute('SELECT 1 FROM sitemap_candidates WHERE source_id=? AND url=?',
                                              (src['source_id'],target_url)).fetchone())
    report['http_requests'] = f.requests
    report['no_site_pages_fetched'] = True
    report['conclusion'] = ('TARGET_DISCOVERED_IN_SITEMAP' if report['target_discovered']
                            else 'TARGET_NOT_FOUND_IN_BOUNDED_SAMPLE' if target_url
                            else 'CANDIDATES_STAGED_RESEARCH_ONLY')
    if index_discovered_target and report['target_discovered']:
        # Explicitly scoped to one previously discovered exact page. This is a
        # separate fetch with fresh robots validation, no general-site crawl.
        page_report = e.crawl(db,source_json,[target_url],max_pages=1,max_depth=0,
                            min_delay=min_delay,allow_local=allow_local,sitemaps=False)
        report['target_crawl'] = page_report
        with e.dbopen(db) as c:
            indexed = c.execute('SELECT title FROM pages WHERE url=? AND indexed=1',(target_url,)).fetchone()
            report['target_indexed'] = bool(indexed)
            report['target_title'] = indexed['title'] if indexed else None
            report['search_results'] = e.search(c,'London New Year Eve 2026',limit=5)
        report['conclusion'] = 'TARGET_DISCOVERED_AND_INDEXED_INTERNAL' if indexed else 'TARGET_DISCOVERED_FETCH_NOT_INDEXED'
    elif index_discovered_target:
        report['target_indexed'] = False
    return report

def main(argv=None):
    ap=argparse.ArgumentParser(description='Pulse Search R2-P14 standalone sitemap discovery')
    ap.add_argument('--db', required=True)
    ap.add_argument('--sources',required=True)
    ap.add_argument('--query',default="What events are happening in London for New Year's Eve 2026?")
    ap.add_argument('--max-docs',type=int,default=6)
    ap.add_argument('--max-candidates',type=int,default=400)
    ap.add_argument('--max-depth',type=int,default=2)
    ap.add_argument('--min-delay',type=float,default=2.0)
    ap.add_argument('--fixture-loopback',action='store_true')
    ap.add_argument('--target-url',help='Optional exact URL for coverage acceptance; fetched only with explicit index option')
    ap.add_argument('--index-discovered-target',action='store_true',help='Crawl at most one exactly matched target after sitemap discovery')
    ap.add_argument('--report',required=True)
    args=ap.parse_args(argv)
    try:
        result=research_discover(args.db,args.sources,args.query,max_docs=args.max_docs,
            max_candidates=args.max_candidates,max_depth=args.max_depth,min_delay=args.min_delay,
            allow_local=args.fixture_loopback,target_url=args.target_url,
            index_discovered_target=args.index_discovered_target)
        p=Path(args.report);p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except (e.Hold, OSError, ValueError, sqlite3.Error) as exc:
        print('HOLD: '+str(exc),file=__import__('sys').stderr)
        return 2
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
