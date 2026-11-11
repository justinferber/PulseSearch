#!/usr/bin/env python3
"""Read-only index QA and query evaluation for the independent Pulse Search engine.

No web requests. The only data it evaluates are pages already in the local index.
No content snippets or bodies are exported. This is a research QA tool, not a claim
of production relevance or web-scale capacity.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import time
from urllib.parse import quote
import pulse_search_engine as engine

VERSION = '0.7.0-r2p5-quality'


@contextmanager
def readonly(db):
    path = Path(db).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError('database_is_not_a_file')
    # Mode=ro avoids accidental schema migration, insert or update.
    conn = sqlite3.connect('file:' + quote(path.as_posix(), safe='/') + '?mode=ro', uri=True, timeout=8)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA query_only=ON')
        yield conn
    finally:
        conn.close()


def _rows(conn, sql, args=()):
    return conn.execute(sql, args).fetchall()


def _counts(conn, table, field):
    return {str(r['value']): r['n'] for r in _rows(conn, f'SELECT {field} value, COUNT(*) n FROM {table} GROUP BY {field} ORDER BY {field}')}


def audit(db):
    """Fail closed for index / FTS inconsistencies and prohibited retained pages."""
    errors=[]
    with readonly(db) as conn:
        check=conn.execute('PRAGMA quick_check').fetchone()[0]
        if check != 'ok': errors.append('sqlite_quick_check_failed')
        foreign_key_errors=conn.execute('PRAGMA foreign_key_check').fetchall()
        if foreign_key_errors: errors.append('foreign_key_violation:'+str(len(foreign_key_errors)))
        for table in ('sources','frontier','pages','page_fts','scheduled_urls','external_candidates','audit'):
            present=conn.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone()
            if not present: raise ValueError('missing_required_table:'+table)
        sources=[dict(r) for r in _rows(conn, 'SELECT source_id,origin,paths,approved,enabled,display_mode,rights_basis FROM sources ORDER BY source_id')]
        active={r['source_id']:r for r in sources if r['approved']==1 and r['enabled']==1}
        per_source={r['source_id']:{'origin':r['origin'],'indexed':0,'stored':0,'frontier':0,'scheduled':0,'mode':r['display_mode']}
                    for r in sources}
        total_bytes=0
        indexed=0;stale=[];page_count=0
        fts_ids={int(r['rowid']) for r in _rows(conn,'SELECT rowid FROM page_fts')}
        for row in _rows(conn,'SELECT id,url,source_id,title,body,content_sha256,duplicate_of,indexed,fetched_at FROM pages ORDER BY id'):
            page_count+=1
            src_id=row['source_id']
            if src_id not in per_source:
                errors.append('unknown_source_for_page:'+str(row['id']));continue
            per_source[src_id]['stored']+=1
            is_indexed=bool(row['indexed'])
            if is_indexed:
                indexed+=1;per_source[src_id]['indexed']+=1
            if src_id not in active:errors.append('retired_or_unapproved_source_retains_page:'+str(row['id']))
            if bool(row['duplicate_of']) and is_indexed:errors.append('duplicate_indexed:'+str(row['id']))
            if (row['id'] in fts_ids) != is_indexed:errors.append('fts_row_mismatch:'+str(row['id']))
            if row['id'] in fts_ids:
                fr=conn.execute('SELECT title,body FROM page_fts WHERE rowid=?',(row['id'],)).fetchone()
                if fr is None or fr['title']!=row['title'] or fr['body']!=row['body']:
                    errors.append('fts_content_mismatch:'+str(row['id']))
            if not engine.scope(row['url'],next((s for s in sources if s['source_id']==src_id),{})):
                errors.append('page_outside_approved_scope:'+str(row['id']))
            if hashlib.sha256((row['title']+'\n'+row['body']).encode('utf-8')).hexdigest()!=row['content_sha256']:
                errors.append('stored_content_hash_mismatch:'+str(row['id']))
            total_bytes+=len(row['title'].encode())+len(row['body'].encode())
            try:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(row['fetched_at'])).total_seconds()/3600
                if age < -0.1:errors.append('future_fetched_timestamp:'+str(row['id']))
                if age > 30*24:stale.append(row['id'])
            except (TypeError,ValueError):errors.append('invalid_fetched_at:'+str(row['id']))
        page_ids={int(r['id']) for r in _rows(conn,'SELECT id FROM pages')}
        for orphan in sorted(fts_ids-page_ids):errors.append('orphan_fts_row:'+str(orphan))
        for row in _rows(conn,'SELECT url,source_id,state FROM frontier'):
            if row['source_id'] not in per_source:errors.append('unknown_frontier_source')
            else: per_source[row['source_id']]['frontier']+=1
        for row in _rows(conn,'SELECT url,source_id,state FROM scheduled_urls'):
            if row['source_id'] not in per_source:errors.append('unknown_scheduled_source')
            else:per_source[row['source_id']]['scheduled']+=1
        bad_sched=conn.execute('''SELECT COUNT(*) FROM scheduled_urls j LEFT JOIN frontier f ON f.url=j.url
            WHERE f.url IS NULL OR f.source_id<>j.source_id''').fetchone()[0]
        if bad_sched: errors.append('scheduler_frontier_inconsistency:'+str(bad_sched))
        for row in _rows(conn,'SELECT source_id,origin,paths,approved,enabled,display_mode,rights_basis FROM sources'):
            if row['display_mode']!='metadata_only':
                # Alert to reviewer, but not intrinsically wrong when explicitly licensed.
                continue
        return {
            'version':VERSION,'status':'PASS' if not errors else 'HOLD',
            'checks':{'sqlite_quick_check':check,'errors':len(errors)},
            'errors':errors[:40],
            'counts':{'indexed_pages':indexed,'stored_pages':page_count,'fts_rows':len(fts_ids),
                      'active_sources':len(active),'total_sources':len(sources),
                      'frontier_states':_counts(conn,'frontier','state'),
                      'scheduler_states':_counts(conn,'scheduled_urls','state'),
                      'candidate_domains':conn.execute('SELECT COUNT(DISTINCT origin) FROM external_candidates').fetchone()[0],
                      'recent_crawl_outcomes':_counts_recent(conn),
                      'approx_title_and_body_bytes':total_bytes,
                      'stale_pages_over_30_days':len(stale)},
            'sources':[dict(source_id=k,**v) for k,v in sorted(per_source.items())],
            'rights_note':'Internal research metadata index; source ownership and commercial reuse must be reviewed separately.',
            'paid_search_api_requests':0
        }


def _counts_recent(conn, cap=200):
    rows=_rows(conn,'SELECT outcome FROM audit ORDER BY id DESC LIMIT ?',(cap,))
    return dict(sorted(Counter(r['outcome'] for r in rows).items()))


def evaluate(db, probes, repeats=3, limit=10):
    if not isinstance(probes,list) or not (1<=len(probes)<=30):raise ValueError('probe_count_invalid')
    if not (1<=repeats<=20 and 1<=limit<=20):raise ValueError('query_budget_invalid')
    report=[]; timings=[]
    with readonly(db) as conn:
        for p in probes:
            if not isinstance(p,dict) or not isinstance(p.get('q'),str) or not (1<=len(p['q'])<=160):
                raise ValueError('bad_probe_query')
            expected=p.get('expected_source_id')
            if expected is not None and (not isinstance(expected,str) or len(expected)>64):raise ValueError('bad_expected_source')
            result=[]
            for i in range(repeats):
                begin=time.perf_counter_ns()
                result=engine.search(conn,p['q'],limit,0)
                timings.append((time.perf_counter_ns()-begin)/1e6)
            rank=next((i+1 for i,v in enumerate(result) if v['source_id']==expected),None) if expected else None
            report.append({'query':p['q'],'expected_source_id':expected,'first_expected_source_rank':rank,
                           'hits':len(result),'top_results':[{'title':r['title'][:120], 'url':r['url'],
                           'source_id':r['source_id']} for r in result[:5]]})
    checked=[r for r in report if r['expected_source_id'] is not None]
    matched=sum(r['first_expected_source_rank'] is not None for r in checked)
    precision=round(matched/len(checked),4) if checked else None
    sorted_ms=sorted(timings)
    p95=sorted_ms[max(0,__import__('math').ceil(len(sorted_ms)*0.95)-1)]
    return {'version':VERSION,'total_queries':len(report),'repeat_per_query':repeats,
            'expected_source_hit_at_10':precision,'expected_source_matched':matched,
            'expected_source_checked':len(checked),
            'latency_ms':{'min':round(sorted_ms[0],3),'median':round(statistics.median(sorted_ms),3),
                          'p95':round(p95,3),'max':round(sorted_ms[-1],3)},
            'queries':report,'scope':'In-index local benchmark only, not internet search or scale benchmark.',
            'paid_search_api_requests':0}


def main(argv=None):
    ap=argparse.ArgumentParser(description='Read-only Pulse Search quality gate and query report')
    sub=ap.add_subparsers(dest='action',required=True)
    for command in ('audit','evaluate'):
        p=sub.add_parser(command);p.add_argument('--db',required=True)
        if command=='evaluate':
            p.add_argument('--probes',required=True);p.add_argument('--repeats',type=int,default=3)
    args=ap.parse_args(argv)
    try:
        if args.action=='audit': report=audit(args.db)
        else:report=evaluate(args.db,json.loads(Path(args.probes).read_text(encoding='utf-8')),args.repeats)
        print(json.dumps(report,indent=2,ensure_ascii=False))
        return 0 if report.get('status','PASS')=='PASS' else 2
    except (ValueError,FileNotFoundError,sqlite3.Error,engine.Hold,json.JSONDecodeError) as e:
        print('HOLD: '+str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
