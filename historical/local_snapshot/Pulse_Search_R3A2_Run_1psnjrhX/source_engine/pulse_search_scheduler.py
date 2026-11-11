#!/usr/bin/env python3
"""Pulse Search R2-P3: persistent, bounded, independent web crawl scheduling.

Standalone stdlib only. One manual cycle at a time. No third-party search API.
A schedule entry never confers new permission to crawl a URL.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import time

import pulse_search_engine as e

VERSION = '0.6.0-r2p4-growth'
POLICY = '''
CREATE TABLE IF NOT EXISTS scheduled_urls(
 url TEXT PRIMARY KEY REFERENCES frontier(url) ON DELETE CASCADE,
 source_id TEXT NOT NULL REFERENCES sources(source_id),
 next_due TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('ready','leased','paused')),
 failures INTEGER NOT NULL DEFAULT 0,
 last_outcome TEXT,
 last_claim TEXT,
 last_completed TEXT,
 lease_token TEXT,
 lease_until TEXT);
CREATE INDEX IF NOT EXISTS idx_due ON scheduled_urls(state,next_due,source_id);
CREATE TABLE IF NOT EXISTS scheduler_lock(
 lock_name TEXT PRIMARY KEY, token TEXT NOT NULL, expires TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS origin_cooldown(
 source_id TEXT PRIMARY KEY REFERENCES sources(source_id) ON DELETE CASCADE,
 next_eligible TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scheduler_runs(
 run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
 attempted INTEGER NOT NULL DEFAULT 0, complete INTEGER NOT NULL DEFAULT 0,
 report_json TEXT);
'''


def now_utc(): return datetime.now(timezone.utc)
def stamp(dt): return dt.isoformat()

def init_schedule(db):
    with e.dbopen(db) as c:
        c.executescript(POLICY)
    return db


def permitted_sources(c):
    return {row['source_id']:row for row in c.execute('SELECT * FROM sources WHERE approved=1 AND enabled=1')}


def permanent_block(reason):
    if not reason:return False
    return (reason in ('robots_disallow','redirect_robots_disallow','redirect_out_of_scope',
                       'non_html_resource','not_html') or
            reason.startswith(('page_http_403','page_http_451','page_http_404','page_http_410',
                              'redirect_out_of_scope','bad_url','query_trap')))


def sync(db,refresh_hours=24.0, now=None):
    if not 1<=refresh_hours<=720:raise e.Hold('refresh_hours_out_of_bounds')
    now=now or now_utc()
    inserted=0
    with e.dbopen(db) as c:
        c.executescript(POLICY)
        srcs=permitted_sources(c)
        for f in c.execute("SELECT f.* FROM frontier f JOIN sources s ON s.source_id=f.source_id WHERE s.approved=1 AND s.enabled=1 ORDER BY f.url"):
            if f['source_id'] not in srcs:continue
            if not e.scope(f['url'],srcs[f['source_id']],allow_local=True): continue
            if c.execute('SELECT 1 FROM scheduled_urls WHERE url=?',(f['url'],)).fetchone(): continue
            if f['state']=='done' and f['last_seen']:
                try: due=datetime.fromisoformat(f['last_seen'])+timedelta(hours=refresh_hours)
                except (ValueError,TypeError): due=now
            elif f['state']=='blocked':
                due=now+timedelta(hours=24)
            else:due=now
            state='paused' if f['state']=='blocked' and permanent_block(f['last_error']) else 'ready'
            c.execute('''INSERT INTO scheduled_urls(url,source_id,next_due,state,last_outcome)
                         VALUES(?,?,?,?,?)''',(f['url'],f['source_id'],stamp(due),state,f['last_error']))
            inserted+=1
    return {'new_schedule_rows':inserted,'refresh_hours':refresh_hours}


def seed(db,source_path,urls,allow_local=False):
    if not urls or len(urls)>100:raise e.Hold('seed_budget_invalid')
    entries=json.loads(Path(source_path).read_text(encoding='utf-8'))
    added=0
    with e.dbopen(db) as c:
        e.register_sources(c,entries,allow_local)
        sources=permitted_sources(c)
        for u in urls:
            matches=[src for src in sources.values() if e.scope(u,src,allow_local)]
            if len(matches)!=1:raise e.Hold('unapproved_seed:'+u[:90])
            if e.enqueue(c,u,matches[0],0,allow_local=allow_local): added+=1
    sync(db)
    return {'new_frontier_urls':added,'submitted_seeds':len(urls)}


def summary(db,now=None):
    now=now or now_utc()
    with e.dbopen(db) as c:
        total={r['state']:r['n'] for r in c.execute('SELECT state,COUNT(*) n FROM scheduled_urls GROUP BY state')}
        due=c.execute('''SELECT COUNT(*) FROM scheduled_urls j JOIN sources s ON s.source_id=j.source_id
                 WHERE state='ready' AND next_due<=? AND s.approved=1 AND s.enabled=1''',(stamp(now),)).fetchone()[0]
        claimable=c.execute('''SELECT COUNT(*) FROM scheduled_urls j JOIN sources s ON s.source_id=j.source_id
                    LEFT JOIN origin_cooldown o ON o.source_id=j.source_id
                    WHERE j.state='ready' AND j.next_due<=? AND s.approved=1 AND s.enabled=1
                    AND (o.next_eligible IS NULL OR o.next_eligible<=?)''',(stamp(now),stamp(now))).fetchone()[0]
        return {'total':sum(total.values()),'states':total,'ready_due':due,'claimable_due':claimable,'search_index':e.stats(c)}


def claim(db,max_pages,max_per_source=2,lease_seconds=900,now=None):
    if not 1<=max_pages<=e.MAX_PAGES:raise e.Hold('cycle_page_budget_invalid')
    if not 1<=max_per_source<=max_pages:raise e.Hold('per_source_budget_invalid')
    if not 180<=lease_seconds<=3600:raise e.Hold('lease_seconds_invalid')
    now=now or now_utc();ts=stamp(now)
    token=secrets.token_hex(18)
    expiry=stamp(now+timedelta(seconds=lease_seconds))
    selected=[]
    with e.dbopen(db) as c:
        c.execute('BEGIN IMMEDIATE')
        # Global lock prevents simultaneous scheduler cycles. Only an expired owner may be superseded.
        old=c.execute("SELECT token,expires FROM scheduler_lock WHERE lock_name='crawler'").fetchone()
        if old and old['expires']>ts:raise e.Hold('scheduler_worker_already_running')
        c.execute("DELETE FROM scheduler_lock WHERE lock_name='crawler'")
        c.execute("INSERT INTO scheduler_lock(lock_name,token,expires) VALUES('crawler',?,?)",(token,expiry))
        # Expired lease recovery; rows keep retry counters.
        c.execute("UPDATE scheduled_urls SET state='ready',lease_token=NULL,lease_until=NULL WHERE state='leased' AND lease_until<=?",(ts,))
        rows=c.execute('''SELECT j.*,f.depth,f.state frontier_state, f.last_error,s.origin
         FROM scheduled_urls j JOIN sources s ON j.source_id=s.source_id
         JOIN frontier f ON j.url=f.url
         LEFT JOIN origin_cooldown o ON o.source_id=j.source_id
         WHERE j.state='ready' AND j.next_due<=? AND s.approved=1 AND s.enabled=1 AND f.depth<=?
         AND (o.next_eligible IS NULL OR o.next_eligible<=?)
         ORDER BY j.next_due,j.url LIMIT 500''',(ts,e.MAX_DEPTH,ts)).fetchall()
        groups=defaultdict(list)
        for row in rows:
            if row['frontier_state']=='blocked' and permanent_block(row['last_error']):
                c.execute("UPDATE scheduled_urls SET state='paused' WHERE url=?",(row['url'],))
                continue
            groups[row['source_id']].append(row)
        # Least recently served sources first, then overdue work within each source.
        sources=sorted(groups,key=lambda sid: (min([r['last_claim'] or '' for r in groups[sid]]) or '', sid))
        used=Counter()
        while len(selected)<max_pages:
            progressed=False
            for sid in sources:
                if not groups[sid] or used[sid]>=max_per_source:continue
                row=groups[sid].pop(0)
                selected.append(row['url']);used[sid]+=1;progressed=True
                c.execute("UPDATE scheduled_urls SET state='leased',lease_token=?,lease_until=?,last_claim=? WHERE url=?",
                          (token,expiry,ts,row['url']))
                c.execute("UPDATE frontier SET state='queued',last_error=NULL WHERE url=?",(row['url'],))
                if len(selected)==max_pages:break
            if not progressed:break
        run_id=secrets.token_hex(12)
        c.execute('INSERT INTO scheduler_runs(run_id,started_at,attempted) VALUES(?,?,?)',(run_id,ts,len(selected)))
    return {'run_id':run_id,'token':token,'urls':selected,'leased_until':expiry,'started_at':ts}


def next_due(outcome,failures,now,refresh_hours):
    if outcome.startswith(('hold:robots_disallow','hold:redirect_robots_disallow','hold:redirect_out_of_scope',
                           'removed_or_denied_403','removed_or_denied_451')):
        return 'paused',now,failures+1
    if outcome.startswith('removed_or_denied_'):
        return 'paused',now,failures+1
    if outcome.startswith('hold:'):
        hours=min(72,0.25*(2**min(failures+1,8)))
        return 'ready',now+timedelta(hours=hours),failures+1
    if outcome in ('not_modified_304','unchanged_content'):
        hours=min(720,refresh_hours*3)
    elif outcome in ('not_indexed','not_indexed_304','empty_content'):
        hours=min(720,refresh_hours*7)
    else:
        hours=refresh_hours
    return 'ready',now+timedelta(hours=hours),0


def finish(db,claimed,report=None,failed=False,refresh_hours=24,now=None,min_delay=0):
    now=now or now_utc();ts=stamp(now)
    token=claimed['token']
    outcomes={}
    with e.dbopen(db) as c:
        c.execute('BEGIN IMMEDIATE')
        lock=c.execute("SELECT token FROM scheduler_lock WHERE lock_name='crawler'").fetchone()
        if not lock or lock['token']!=token:raise e.Hold('scheduler_lease_lost')
        # Per-URL outcomes from the persistent audit after the claim; bounded by selected URLs.
        for url in claimed['urls']:
            row=c.execute('''SELECT outcome,detail FROM audit WHERE url=? AND at_utc>=?
                        ORDER BY id DESC LIMIT 1''',(url,claimed.get('started_at',''))).fetchone()
            if row:
                out=row['outcome']
                if out=='hold':out='hold:'+str(row['detail'])
                if out=='removed_or_denied':out='removed_or_denied_'+str(row['detail'])
            else:out='hold:interrupted' if failed else 'hold:not_attempted'
            outcomes[url]=out
            prev=c.execute('SELECT failures FROM scheduled_urls WHERE url=? AND lease_token=?',(url,token)).fetchone()
            if not prev:raise e.Hold('schedule_row_lost')
            state,due,fails=next_due(out,prev['failures'],now,refresh_hours)
            c.execute('''UPDATE scheduled_urls SET state=?,next_due=?,failures=?,last_outcome=?,last_completed=?,
                       lease_token=NULL,lease_until=NULL WHERE url=? AND lease_token=?''',
                     (state,stamp(due),fails,out,ts,url,token))
            # A failed crash/unattempted page stays available for the next retry, not lost.
            if out in ('hold:interrupted','hold:not_attempted'):
                c.execute("UPDATE frontier SET state='blocked',last_error=?,last_seen=? WHERE url=?",
                          (out,ts,url))
        # Persist per-origin polite delay ACROSS processes and scheduler cycles, taking
        # any robots crawl-delay reported by the crawler into account.
        for url in claimed['urls']:
            src=c.execute('''SELECT s.source_id,s.origin FROM frontier f
               JOIN sources s ON s.source_id=f.source_id WHERE f.url=?''',(url,)).fetchone()
            if src is None:continue
            delay=max(min_delay,float((report or {}).get('effective_origin_delays',{}).get(src['origin'],min_delay)))
            earliest=stamp(now+timedelta(seconds=delay))
            c.execute('''INSERT INTO origin_cooldown(source_id,next_eligible) VALUES(?,?)
                  ON CONFLICT(source_id) DO UPDATE SET next_eligible=MAX(next_eligible,excluded.next_eligible)''',
                  (src['source_id'],earliest))
        c.execute("DELETE FROM scheduler_lock WHERE lock_name='crawler' AND token=?",(token,))
        c.execute('UPDATE scheduler_runs SET ended_at=?,complete=?,report_json=? WHERE run_id=?',
                  (ts,1,json.dumps({'outcomes':outcomes,'crawler':report}),claimed['run_id']))
    return outcomes


def run_cycle(db,sources_path,max_pages=4,max_per_source=2,refresh_hours=24,
              min_delay=2.0,allow_local=False):
    if min_delay<1.5 and not allow_local:raise e.Hold('live_delay_too_short')
    init_schedule(db)
    sync_result=sync(db,refresh_hours)
    claimed=claim(db,max_pages,max_per_source)
    crawl_report=None;failed=False
    try:
        if claimed['urls']:
            crawl_report=e.crawl(db,sources_path,[],max_pages=len(claimed['urls']),max_depth=e.MAX_DEPTH,
                                min_delay=min_delay,allow_local=allow_local,scheduled_urls=claimed['urls'])
    except BaseException:
        failed=True
        raise
    finally:
        finish(db,claimed,crawl_report,failed,refresh_hours,min_delay=min_delay)
    fresh=sync(db,refresh_hours)
    return {'version':VERSION,'run_id':claimed['run_id'], 'selected_urls':len(claimed['urls']),
            'initial_synchronised':sync_result['new_schedule_rows'],
            'newly_discovered_urls':fresh['new_schedule_rows'],
            'crawl':crawl_report,'schedule_outcomes':summary(db),
            'paid_search_api_requests':0,'external_search_engine_calls':0}



def run_bounded_loop(db,sources_path,cycles=2,interval_seconds=60,**kwargs):
    """Supervised bounded multi-cycle operation; not an unattended daemon."""
    if not 1<=cycles<=20:raise e.Hold('cycles_out_of_bounds')
    if not 0<=interval_seconds<=3600:raise e.Hold('interval_out_of_bounds')
    if not kwargs.get('allow_local',False) and interval_seconds<30 and cycles>1:
        raise e.Hold('live_loop_interval_below_30_seconds')
    output=[]
    for i in range(cycles):
        if i:time.sleep(interval_seconds)
        output.append(run_cycle(db,sources_path,**kwargs))
    return {'version':VERSION,'completed_cycles':len(output),'total_selected':sum(x['selected_urls'] for x in output),
            'cycles':[{'run_id':x['run_id'],'selected_urls':x['selected_urls'],
                       'newly_discovered_urls':x['newly_discovered_urls'],
                       'crawl':x['crawl']} for x in output],
            'final':summary(db),'paid_search_api_requests':0}

def main():
    ap=argparse.ArgumentParser(description='Pulse Search independent persistent crawl scheduler')
    sp=ap.add_subparsers(dest='action',required=True)
    for name in ('init','stats','seed','cycle','loop'):
        p=sp.add_parser(name);p.add_argument('--db',required=True)
        if name in ('seed','cycle','loop'):p.add_argument('--sources',required=True)
        if name=='seed':
            p.add_argument('--seed',action='append',required=True)
            p.add_argument('--fixture-loopback',action='store_true')
        if name in ('cycle','loop'):
            p.add_argument('--max-pages',type=int,default=4)
            p.add_argument('--max-per-source',type=int,default=2)
            p.add_argument('--refresh-hours',type=float,default=24)
            p.add_argument('--min-delay',type=float,default=2)
            p.add_argument('--fixture-loopback',action='store_true')
        if name=='loop':
            p.add_argument('--cycles',type=int,default=2)
            p.add_argument('--interval-seconds',type=float,default=60)
    a=ap.parse_args()
    try:
        if a.action=='init':e.initdb(a.db);init_schedule(a.db); result={'ready':True}
        elif a.action=='stats': result=summary(a.db)
        elif a.action=='seed':result=seed(a.db,a.sources,a.seed,a.fixture_loopback)
        elif a.action=='cycle':result=run_cycle(a.db,a.sources,a.max_pages,a.max_per_source,a.refresh_hours,a.min_delay,a.fixture_loopback)
        else:result=run_bounded_loop(a.db,a.sources,a.cycles,a.interval_seconds,
                   max_pages=a.max_pages,max_per_source=a.max_per_source,refresh_hours=a.refresh_hours,
                   min_delay=a.min_delay,allow_local=a.fixture_loopback)
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except (e.Hold,ValueError,sqlite3.Error) as exc:
        print('HOLD: '+str(exc),file=sys.stderr);return 2
    return 0

if __name__=='__main__':sys.exit(main())
