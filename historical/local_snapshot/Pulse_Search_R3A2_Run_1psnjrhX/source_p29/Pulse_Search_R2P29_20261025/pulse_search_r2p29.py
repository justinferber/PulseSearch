#!/usr/bin/env python3
"""R2-P29 experimental topic/year/title ranker. READ-ONLY, no network, no publication.

The intentionally bounded 12-query pilot is NOT a generic solved web ranker.
All acceptance claims remain offline research and any new result without prior human
relevance assessment is explicitly UNGRADED.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import html
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import quote, urlsplit, unquote

VERSION='R2-P29-120Page-Shadow-v1'
REQUIRED_OLD_INDEX_SHA='f93a17ee28d22d7fec18063597fba3b4eecfc8fd67cafcc8e0b5f354bf3c2739'
REPORT_SHA='5b343dc1710663e248a958f486f293a1af67702ebe8980aa7b31641ad05e6787'
CORRECTED_REVIEW_SHA='c398c2ea78bbb27c1899d4544e70bbb7805258cfda1e0c84937e02990fdc5ba2'
TOPICS=('healthcare','public_services','web_development','london_events','identity_documents','live_local')
QUESTIONS=(
 ('healthcare','How can I book an NHS blood test in England?',True),
 ('healthcare','How can I register with a GP surgery?',True),
 ('public_services','What council tax band is my property in?',True),
 ('public_services','Where can I register to vote?',True),
 ('web_development','Where can I learn JavaScript programming?',True),
 ('web_development','What is HTTP?',True),
 ('london_events',"What events are happening in London for New Year's Eve 2026?",False),
 ('london_events','What is Diwali on the Square in London 2026?',False),
 ('identity_documents','How do I renew my UK adult passport online?',False),
 ('identity_documents','How do I apply for a first provisional driving licence?',False),
 ('live_local','Which vegan shoe shops in Manchester are open now?',False),
 ('live_local','Will it rain in Newbury tomorrow?',False),
)
# Linguistic stopwords only. Not a domain allowlist nor a known-answer URL lookup.
STOPWORDS=frozenset('a an and are as at be by can do does for from how i in is it my of on or our the their there this to what where which who will with your uk england london online happening happen events event now today tomorrow please shop shops'.split())
DYNAMIC_NOW=re.compile(r'\b(?:open\s+now|opening\s+hours|in\s+stock\s+(?:now|today)|available\s+now|live\s+prices?|weather|forecast|rain|snow|tomorrow)\b',re.I)
YEARS=re.compile(r'(?<!\d)(20(?:1\d|2\d|3\d))(?!\d)')
VALID_ORIGINS={'https://www.london.gov.uk','https://www.nhs.uk','https://www.gov.uk','https://developer.mozilla.org','https://docs.python.org','https://www.rfc-editor.org','https://www.legislation.gov.uk'}
class Hold(Exception):pass

def sha(path):
    h=sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def require_sha(path,expected):
    digest=sha(path)
    if digest!=expected:raise Hold(f'SHA_MISMATCH:{Path(path).name}:{digest}')

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def words(s):
    # Curly apostrophes, URL escapes, Unicode punctuation -> discrete words.
    s=unquote(str(s)).casefold().replace('’',"'")
    s=re.sub(r"([a-z])['’]s\b",r'\1s',s) # new year's -> years
    return [w for w in re.findall(r'[^\W_]+',s,flags=re.UNICODE)]

def stem(s):
    if s in ('years','year'):return 'year'
    if s in ('new','newspapers'):return s
    if s in ('licence','licenses','license','licences'):return 'licence'
    if len(s)>5 and s.endswith('ies'):return s[:-3]+'y'
    if len(s)>4 and s.endswith('es') and s[:-2] in ('box','tax','dress'):return s[:-2]
    if len(s)>3 and s.endswith('s') and not s.endswith(('ss','us')):return s[:-1]
    return s

def relevant_terms(q):
    raw=words(q)
    year={w for w in raw if YEARS.fullmatch(w)}
    return [stem(w) for w in raw if w not in STOPWORDS and w not in year]

def dynamic_intent(q):
    return bool(DYNAMIC_NOW.search(q))

def title_score(q,title,url):
    wanted=relevant_terms(q)
    if not wanted:return (False,0,'NO_SUBJECT_TERMS',{})
    requested=set(YEARS.findall(q))
    path=urlsplit(url).path
    tt=words(title); pt=words(path)
    t={stem(w) for w in tt};p={stem(w) for w in pt}; present=t|p
    match=set(wanted)&present
    titleyears=set(YEARS.findall(title));pathyears=set(YEARS.findall(path))
    # A year explicitly requested by the user must be supported by the event's
    # own title or URL identity, rather than incidental year in page body.
    if requested and not (requested & (titleyears|pathyears)):
        return (False,0,'REQUESTED_YEAR_NOT_IN_TITLE_OR_PATH',{'requested':sorted(requested),'title_years':sorted(titleyears)})
    if requested and (titleyears-requested):
        return (False,0,'CONFLICTING_EVENT_EDITION_YEAR',{'requested':sorted(requested),'title_years':sorted(titleyears)})
    coverage=len(match)/len(set(wanted))
    # When the query has multiple meaningful anchors, reject matches based on
    # one generic word. Short queries require matching their single subject.
    minimum=1 if len(set(wanted))==1 else 2
    if requested and len(match)<len(set(wanted)):
        return (False,0,'NAMED_EVENT_ANCHOR_INCOMPLETE',{'matches':sorted(match),'wanted':sorted(set(wanted))})
    if len(match)<minimum or coverage<0.5:
        return (False,0,'INSUFFICIENT_TITLE_PATH_SUBJECT_MATCH',{'matches':sorted(match),'wanted':sorted(set(wanted))})
    # Favor short exact subject titles; pages about event services remain eligible
    # but below a canonical named-event page.
    title_matches=sum(w in t for w in set(wanted))
    exactish=1 if all(w in t for w in set(wanted)) else 0
    extra=max(0,len(set(stem(w) for w in tt))-len(set(wanted))-3)
    penalty=8 if re.search(r'\b(?:information for|businesses and residents|consultation)\b',title,re.I) else 0
    score=title_matches*10 + len(match)*6 + exactish*7 + int(coverage*12) + (18 if requested else 0) - extra*0.4 - penalty
    return (True,score,'TITLE_PATH_SUBJECT_AND_YEAR_MATCH',{'matches':sorted(match),'wanted':sorted(set(wanted)),'year':sorted(requested),'coverage':round(coverage,3)})

def owner_ro(path):
    p=Path(path).resolve(strict=True)
    if not p.is_file() or p.is_symlink() or p.stat().st_size > 500_000_000:raise Hold('UNSAFE_INDEX_FILE')
    c=sqlite3.connect('file:'+quote(str(p),safe='/')+'?mode=ro&immutable=1',uri=True,timeout=10)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c

def check_owner_index(conn,source_report):
    if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise Hold('INDEX_INTEGRITY_FAILURE')
    indexed=conn.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
    fts=conn.execute('SELECT COUNT(*) FROM page_fts').fetchone()[0]
    sources=conn.execute('SELECT COUNT(DISTINCT source_id) FROM pages WHERE indexed=1').fetchone()[0]
    if (indexed,fts,sources)!=(120,120,7):raise Hold(f'INDEX_SCOPE_MISMATCH:{indexed}/{fts}/{sources}')
    if source_report.get('status')!='LIVE_100_NEW_INDEXED_CLONE_ONLY_PASS' or (source_report.get('newly_indexed'),source_report.get('indexed_pages_after'),source_report.get('existing_index_pages'))!=(103,120,17):raise Hold('SOURCE_REPORT_SCOPE_MISMATCH')
    new=source_report.get('new_pages')
    if not isinstance(new,list) or len(new)!=103 or len({x['url'] for x in new})!=103:raise Hold('SOURCE_NEW_PAGES_INCONSISTENT')
    for item in new:
        url=item['url'];title=item['title']
        if not url.startswith('https://www.london.gov.uk/events/'):
            raise Hold('SOURCE_URL_SCOPE_VIOLATION')
        rows=conn.execute('SELECT title,indexed FROM pages WHERE url=?',(url,)).fetchall()
        if len(rows)!=1 or rows[0]['indexed']!=1 or rows[0]['title']!=title:raise Hold('SOURCE_PAGE_MISSING_OR_CHANGED:'+url)
    if conn.execute("SELECT COUNT(*) FROM sources WHERE approved<>1 AND source_id IN (SELECT source_id FROM pages WHERE indexed=1)").fetchone()[0]:raise Hold('UNAPPROVED_SOURCE')
    return {'indexed':indexed,'fts_rows':fts,'sources':sources,'bound_new_pages':103}

def retrieve(conn,query,limit=200):
    # Use accepted engine's own FTS5 table. Query evaluation is read-only.
    # Max 200 is research only: report candidate limit transparently.
    import pulse_search_p10 as p10
    toks=p10.tokenize(query)
    if not toks:return []
    match=' OR '.join('"'+t.replace('"','')+'"' for t in toks)
    sql='''SELECT p.url,p.title,p.source_id, bm25(page_fts,6.0,1.0) AS rank
           FROM page_fts JOIN pages p ON p.id=page_fts.rowid
           JOIN sources s ON s.source_id=p.source_id
           WHERE page_fts MATCH ? AND p.indexed=1 AND s.approved=1 AND s.enabled=1
           ORDER BY rank ASC,p.url ASC LIMIT ?'''
    return [dict(r) for r in conn.execute(sql,(match,limit))]

def shadow_rank(q,candidates,limit=3):
    if dynamic_intent(q):return [],'WITHHELD_UNVERIFIED_LIVE_DATA',[]
    accepted=[];removed=[]
    for row in candidates:
        ok,score,reason,ex=title_score(q,row['title'],row['url'])
        record={'url':row['url'],'title':row['title'],'source_id':row.get('source_id'), 'shadow_score':round(score,3)}
        if ok:accepted.append((score,float(row.get('rank',0)),record))
        else:removed.append({'url':row['url'],'title':row['title'],'reason':reason})
    accepted.sort(key=lambda r:(-r[0],r[1],r[2]['url']))
    results=[x[2] for x in accepted[:limit]]
    return results,('MATCHES_UNVERIFIED' if results else 'WITHHELD_NO_STRONG_TITLE_PATH_MATCH'),removed

def assessment(shadow_queries,review):
    refs={q['query']:q for q in review['questions']}
    gradecounts=Counter();failures=[];changes=[];unknown=0
    for row in shadow_queries:
        q=row['query']; prior=refs[q]
        graded={r['url']:r['grade'] for r in prior['results']}
        goodtop=(prior['results'] and prior['results'][0]['grade']>=2)
        newtop=row['shadow'][0]['url'] if row['shadow'] else None
        oldtop=prior['results'][0]['url'] if prior['results'] else None
        if goodtop and newtop!=oldtop:failures.append('KNOWN_USEFUL_TOP1_NOT_RETAINED:'+q)
        if row['topic']=='live_local' and row['shadow']:failures.append('LIVE_LOCAL_NOT_WITHHELD:'+q)
        if q.startswith('What events are happening in London for New Year') and newtop!=oldtop:failures.append('NYE_2026_NOT_RESTORED')
        if (row['shadow'][0]['url'] if row['shadow'] else None)!=(row['baseline'][0]['url'] if row['baseline'] else None):changes.append(q)
        for result in row['shadow']:
            g=graded.get(result['url'])
            result['previous_human_grade']=g
            if g is None:unknown+=1
            else:
                gradecounts[g]+=1
                if g==0:failures.append('PREVIOUS_HUMAN_IRRELEVANT_RESULT_SHOWN:'+q+':'+result['url'])
    return {'preserved_known_useful_top1_target':9,'known_useful_top1_violations':len([f for f in failures if f.startswith('KNOWN_USEFUL_TOP1')]),'graded_shadow_results':sum(gradecounts.values()),'ungraded_shadow_results':unknown,'previous_human_grades':{str(i):gradecounts[i] for i in range(4)},'first_result_changes':changes,'gate_issues':failures}

def render(report):
    page=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pulse Search R2-P29 · 120-page ranking audit</title><style>body{font:15px/1.55 system-ui,Segoe UI,Arial;background:#f4f7f8;color:#172333;margin:0}main{max-width:1100px;margin:auto;padding:30px 18px 90px}h1{font-size:29px}header{background:#12394b;color:#fff;border-radius:15px;padding:22px 28px}header p{color:#d9edf1}section{border:1px solid #d7e3e7;border-radius:12px;background:#fff;padding:15px 19px;margin:15px 0}p{margin:8px 0}ul{margin:10px 0;padding-left:22px}.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.tag{display:inline-block;background:#e6edf1;border-radius:6px;padding:2px 7px;font-size:12px}small{color:#5f6c78}a{overflow-wrap:anywhere;color:#185e83}.warning{background:#fff0df;padding:10px;border-radius:7px}.hit{border-bottom:1px solid #dce5e7;padding:8px 0}strong{font-weight:650}h2{font-size:19px}</style></head><body><main><header><small style="color:#d9edf1">PULSE SEARCH · INDEPENDENT SEARCH ENGINE · RESEARCH ONLY</small><h1>R2-P29 — Does relevance improve on 120 pages?</h1><p>Current broad-OR ranker versus title/topic/year-gated shadow ranking. Offline read-only run; not a production ranking update.</p></header>']
    v=report['verification'];a=report['evaluation']
    page.append('<section><b>Status: '+html.escape(report['status'])+'</b><p>Indexed: '+str(v['indexed'])+' · Publishers: '+str(v['sources'])+' · New pages bound: '+str(v['bound_new_pages'])+' · Paid API calls: 0</p><p>Known previously useful top1 retained target: 9; violations: '+str(a['known_useful_top1_violations'])+' · Ungraded shadow results: '+str(a['ungraded_shadow_results'])+'</p><p class="warning">Human ratings apply only to the previously reviewed URLs. New or unreviewed pages are not automatically judged to answer questions. Static crawled pages cannot verify weather, shop hours, or availability.</p></section>')
    for row in report['questions']:
        page.append('<section><small class="tag">'+html.escape(row['topic'])+'</small><h2>'+html.escape(row['query'])+'</h2><div class="cols">')
        for k,title in [('baseline','Accepted R2-P27C first three'),('shadow','R2-P29 experimental first three')]:
            page.append('<div><strong>'+title+'</strong>')
            if not row[k]:page.append('<p>No returned matches</p>')
            for i,r in enumerate(row[k],1):
                grade=r.get('previous_human_grade')
                s=(' · earlier human grade '+str(grade)) if grade is not None else (' · not human graded' if k=='shadow' else '')
                page.append('<div class="hit"><small>#'+str(i)+s+'</small><div><strong>'+html.escape(r['title'])+'</strong></div><a target="_blank" rel="noopener noreferrer" href="'+html.escape(r['url'],quote=True)+'">'+html.escape(r['url'])+'</a></div>')
            page.append('</div>')
        page.append('</div><p><small>Shadow status: '+html.escape(row['shadow_status'])+' · Candidate pool: '+str(row['fts_candidates'])+' · Suppressed from experimental pool: '+str(row['filtered_candidates'])+'</small></p></section>')
    page.append('<section><p><strong>Limits:</strong> Query matrix intentionally only 12 questions, one publisher contributed the 103 new documents, and no content-use licence is inferred. The experiment uses FTS5 retrieval + title/path/topic gates, not semantic understanding or current-information verification.</p></section></main></body></html>')
    return '\n'.join(page)

def run(owner_index,live_report,human_review,out):
    if not Path(owner_index).is_file():raise Hold('OWNER_INDEX_NOT_FOUND')
    require_sha(live_report,REPORT_SHA);require_sha(human_review,CORRECTED_REVIEW_SHA)
    source=read_json(live_report);human=read_json(human_review)
    if human.get('source_audit_sha256')!='0bb30987d91db818d18b70ce567d8c0df701e13325888cfae4d0533688835987':raise Hold('HUMAN_REVIEW_PROVENANCE_MISMATCH')
    # Original twelve questions reproduced from the accepted R2-P23 source and
    # fully bound against the corrected user review and the live R2-P27C report.
    if len(QUESTIONS)!=12 or len(human.get('questions',[]))!=12 or len(source.get('query_samples',[]))!=12:raise Hold('BENCHMARK_SHAPE_DRIFT')
    report_map={x['query']:x for x in source['query_samples']}
    if len(report_map)!=12 or set(report_map)!={q for _,q,_ in QUESTIONS}:raise Hold('SOURCE_QUERY_SET_DRIFT')
    oldhash=sha(owner_index)
    with closing(owner_ro(owner_index)) as conn:
        verify=check_owner_index(conn,source)
        actual=[]
        for i,(topic,q,old) in enumerate(QUESTIONS):
            sr=report_map[q]
            if human['questions'][i]['query']!=q or human['questions'][i]['topic']!=topic:raise Hold('QUERY_ORDER_OR_IDENTITY_DRIFT')
            import pulse_search_engine as engine
            prev=engine.search(conn,q,limit=3)
            reportprev=sr.get('results',[])
            if [(h['url'],h['title']) for h in prev]!=[(h['url'],h['title']) for h in reportprev]:raise Hold('CURRENT_RESULTS_NOT_REPRODUCIBLE:'+q)
            candidates=retrieve(conn,q)
            exp,status,removed=shadow_rank(q,candidates)
            actual.append({'id':f'search_{i+1:02d}','topic':topic,'query':q,'baseline':[{'url':h['url'],'title':h['title']} for h in prev],
                           'shadow':exp,'shadow_status':status,'fts_candidates':len(candidates),'filtered_candidates':len(removed),
                           'filter_reasons':dict(Counter(x['reason'] for x in removed)),
                           'shadow_human_assessment':'PRIOR_GRADES_ONLY_NEW_URLS_UNGRADED'})
    if sha(owner_index)!=oldhash:raise Hold('INDEX_CHANGED_DURING_READ_ONLY_EXPERIMENT')
    evals=assessment(actual,human)
    result={'version':VERSION,'status':'READ_ONLY_SHADOW_RESEARCH_PASS' if not evals['gate_issues'] else 'HOLD_KNOWN_HUMAN_QUALITY_GATE',
            'verification':verify,'owner_index_sha256_before_after':oldhash,
            'source_report_sha256':REPORT_SHA,'corrected_review_sha256':CORRECTED_REVIEW_SHA,
            'paid_provider_calls':0,'public_network_requests':0,'original_database_writes':0,
            'evaluation':evals,'questions':actual,
            'limitations':['Known useful first results judged only against earlier human grades of original 17-page study',
                           'Newly indexed pages have NOT been independently human relevance graded',
                           'Exact word/title/year filtering may withhold legitimate titles or miss paraphrases',
                           'Not production- or commercial-display-approved; no source rights inferred',
                           'FTS candidate cap 200; no evidence of web-scale performance or recall']}
    dest=Path(out)
    if dest.exists():raise Hold('OUTPUT_FOLDER_ALREADY_EXISTS')
    dest.mkdir(parents=True)
    (dest/'r2p29_shadow_report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (dest/'r2p29_shadow_review.html').write_text(render(result),encoding='utf-8')
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--owner-index',required=True);ap.add_argument('--live-report',required=True);ap.add_argument('--corrected-review',required=True);ap.add_argument('--out',required=True)
    a=ap.parse_args()
    try:
        res=run(a.owner_index,a.live_report,a.corrected_review,a.out)
        print(json.dumps({'status':res['status'],'owner_index_sha256':res['owner_index_sha256_before_after'],'indexed_pages':res['verification']['indexed'],
            'known_useful_top1_violations':res['evaluation']['known_useful_top1_violations'], 'new_or_ungraded_results':res['evaluation']['ungraded_shadow_results'],
            'issues':res['evaluation']['gate_issues'],'new_network_requests':0,'paid_search_api_calls':0,'original_db_writes':0},indent=2))
        print('REPORT='+str(Path(a.out)/'r2p29_shadow_report.json'))
        print('HTML='+str(Path(a.out)/'r2p29_shadow_review.html'))
        return 0 if res['status']=='READ_ONLY_SHADOW_RESEARCH_PASS' else 2
    except (Hold,OSError,sqlite3.Error,KeyError,ValueError,TypeError) as e:
        print('HOLD_R2P29:'+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
