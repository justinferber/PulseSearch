#!/usr/bin/env python3
"""R2-P15 read-only, query-time candidate re-evaluation.

Does not crawl, resolve DNS, index pages, modify the database, or interact
with external search providers. Candidate URLs are NOT verified search results.
"""
from __future__ import annotations
import argparse
import html
import json
import math
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit, unquote
from collections import Counter

VERSION = '0.15.0-r2p15-offline-candidate-review'
STOP = frozenset('a an and are at be can do does for from happening how i in is it me my near of on or the this to what when where which who why with you your events event happening find show list best open now'.split())
YEAR_RE = re.compile(r'(?<!\d)20(?:[2-4]\d)(?!\d)')
MAX_CANDIDATES = 20000
MAX_QUERIES = 20
MAX_RESULTS = 10

class Hold(ValueError):
    pass

def tokenize(value):
    return tuple(x for x in re.findall(r'[a-z0-9]+',value.casefold()) if x not in STOP)

def url_terms(url):
    p=urlsplit(url)
    # Decode solely for analysis; never execute, fetch or reconstruct the decoded URL.
    return tokenize(unquote(p.path)), p.path.lower()

def score_urls(candidates, query, limit=5):
    if not isinstance(query,str) or not (2 <= len(query.strip()) <= 180):
        raise Hold('bad_query')
    if not 1 <= limit <= MAX_RESULTS:
        raise Hold('result_limit')
    terms = set(tokenize(query))
    if not terms:
        return []
    doc_tokens = [set(url_terms(x['url'])[0]) for x in candidates]
    N=max(1,len(candidates))
    df=Counter(t for tokens in doc_tokens for t in tokens)
    query_years = set(YEAR_RE.findall(query))
    result=[]
    for c, ts in zip(candidates,doc_tokens):
        matched=terms & ts
        if not matched:continue
        url_years = set(YEAR_RE.findall(unquote(urlsplit(c['url']).path)))
        if query_years and url_years and query_years.isdisjoint(url_years):
            continue
        # Matching a discriminative term contributes more than common terms.
        score = sum(1.0 + math.log1p((N+1)/(df[t]+1)) for t in matched)
        fraction=len(matched)/len(terms)
        score += 3*fraction
        if query_years and query_years.issubset(url_years):score+=2.5
        # Favor phrase alignment without assuming any particular search subject.
        parts='-'.join(url_terms(c['url'])[0])
        original_terms=list(tokenize(query))
        if len(original_terms)>=2 and '-'.join(original_terms) in parts:score+=3
        # Query-word coverage protects against a ubiquitous term dominating.
        if len(matched)<2 and len(terms)>=3:continue
        result.append({'url':c['url'],'source_id':c['source_id'],
                       'matched_terms':sorted(matched),
                       'query_term_coverage':round(fraction,4),
                       'url_pattern_score':round(score,4),
                       'status':'UNVERIFIED_URL_CANDIDATE'})
    result.sort(key=lambda x:(-x['url_pattern_score'],-x['query_term_coverage'],x['url']))
    return result[:limit]

def read_candidates(dbfile, expected_source):
    p=Path(dbfile).expanduser().resolve(strict=True)
    if not p.is_file() or p.stat().st_size > 2_000_000_000:
        raise Hold('db_missing_or_too_large')
    # read-only URI prevents accidental mutation even if the caller made a mistake.
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=3)
    c.row_factory=sqlite3.Row
    try:
        c.execute('PRAGMA query_only=ON')
        tbl={x[0] for x in c.execute('SELECT name FROM sqlite_master WHERE type="table"')}
        if not {'sources','sitemap_candidates'}.issubset(tbl):
            raise Hold('not_sitemap_discovery_db')
        src=c.execute('SELECT source_id,origin,paths,enabled,approved,display_mode,rights_basis FROM sources WHERE source_id=?',
                      (expected_source,)).fetchone()
        if not src or not src['enabled'] or not src['approved']:
            raise Hold('missing_or_disabled_source')
        try:paths=json.loads(src['paths'])
        except (TypeError,ValueError):raise Hold('invalid_scope')
        if not isinstance(paths,list) or not paths:raise Hold('invalid_scope')
        cnt=c.execute('SELECT count(*) FROM sitemap_candidates WHERE source_id=?',(expected_source,)).fetchone()[0]
        if cnt>MAX_CANDIDATES:raise Hold('candidate_cap_exceeded')
        rows=c.execute('SELECT source_id,url FROM sitemap_candidates WHERE source_id=? ORDER BY url',
                       (expected_source,)).fetchall()
        candidates=[]
        for x in rows:
            u=x['url']; v=urlsplit(u)
            if v.scheme != 'https' or (v.scheme+'://'+v.netloc).lower()!=src['origin'].lower():
                raise Hold('out_of_scope_candidate')
            if not any(root=='/' or v.path==root or v.path.startswith(root.rstrip('/')+'/') for root in paths):
                raise Hold('out_of_scope_candidate')
            candidates.append({'source_id':x['source_id'],'url':u})
        page_count=c.execute('SELECT count(*) FROM pages WHERE indexed=1').fetchone()[0] if 'pages' in tbl else 0
        return candidates, {'source_id':src['source_id'],'origin':src['origin'],
                  'display_mode':src['display_mode'], 'rights_basis':src['rights_basis'],
                  'approved_scope_paths':paths,'indexed_pages_in_research_db':page_count}
    finally:c.close()

def create_report(dbfile, expected_source, questions, limit=5):
    if not isinstance(questions,list) or not 1 <= len(questions) <= MAX_QUERIES:
        raise Hold('bad_questions_list')
    qs=[]
    for q in questions:
        if not isinstance(q,str) or not q.strip() or len(q)>180 or q in qs:
            raise Hold('invalid_or_duplicate_query')
        qs.append(q)
    candidates, source=read_candidates(dbfile,expected_source)
    results=[{'query':q,'matches':score_urls(candidates,q,limit),
              'match_count_in_top':0} for q in qs]
    for r in results:r['match_count_in_top']=len(r['matches'])
    return {'version':VERSION,'status':'READ_ONLY_URL_CANDIDATE_REVIEW',
      'disclaimer':'A sitemap URL is a lead, not a crawled or verified webpage. No result is approved for public display.',
      'source':source, 'staged_url_count':len(candidates),
      'questions':results, 'external_network_calls':0,'paid_search_calls':0,
      'index_writes':0}

def html_report(report):
    out=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P15 offline candidate review</title>',
    '<style>body{font:16px system-ui,sans-serif;max-width:1080px;margin:2rem auto;padding:0 1rem;line-height:1.5}article{border:1px solid #bbb;border-radius:10px;padding:1rem;margin:1.5rem 0}li{margin:.7rem 0;overflow-wrap:anywhere}small{color:#555}.notice{background:#fff3d2;padding:.8rem;border-radius:8px}h2{font-size:1.2rem}</style>',
    '<h1>Pulse Search — Offline candidate research</h1>',
    '<p class="notice">These are unverified sitemap URL leads. They are NOT verified webpage results or commercial display authorisations. This report performs no internet requests.</p>',
    '<p>Staged URLs: '+str(report['staged_url_count'])+' | Approved research source: '+html.escape(report['source']['source_id'])+'</p>']
    for item in report['questions']:
        out.append('<article><h2>Search question: '+html.escape(item['query'])+'</h2>')
        if not item['matches']:out.append('<p>No matching candidate URL in the currently staged set. This is not proof the internet has no answer.</p>')
        else:
            out.append('<ol>')
            for m in item['matches']:
                out.append('<li><code>'+html.escape(m['url'])+'</code> <small>Matched URL terms: '+html.escape(', '.join(m['matched_terms']))+'; pattern score '+str(m['url_pattern_score'])+'; unverified</small></li>')
            out.append('</ol>')
        out.append('</article>')
    out.append('</html>')
    return '\n'.join(out)+'\n'

def main(argv=None):
    p=argparse.ArgumentParser(description='R2-P15 offline URL candidate analysis; no network')
    p.add_argument('--db',required=True);p.add_argument('--source',required=True)
    p.add_argument('--queries',required=True);p.add_argument('--report-dir',required=True)
    args=p.parse_args(argv)
    try:
        queries=json.loads(Path(args.queries).read_text(encoding='utf-8'))
        if isinstance(queries,dict):queries=queries.get('queries')
        result=create_report(args.db,args.source,queries)
        out=Path(args.report_dir);out.mkdir(parents=True,exist_ok=True)
        (out/'candidate_report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        (out/'candidate_review.html').write_text(html_report(result),encoding='utf-8')
        print(json.dumps({'status':result['status'],'source_id':args.source,
            'staged_url_count':result['staged_url_count'],
            'questions':[(q['query'],q['match_count_in_top']) for q in result['questions']],
            'report':str(out/'candidate_report.json'),'html':str(out/'candidate_review.html'),
            'external_network_calls':0,'paid_search_calls':0},indent=2))
    except (Hold, OSError, sqlite3.Error,ValueError) as exc:
        print('HOLD: '+str(exc),file=__import__('sys').stderr)
        return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
