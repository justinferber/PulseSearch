#!/usr/bin/env python3
"""R2-P19: research-only, read-only verification of live-data abstention.

No network requests, provider calls, DB writes, or production-search modifications.
The *static* 14-page research index has no evidence of live stock, current weather,
or establishment opening hours, so lexical coincidences cannot answer those intents.
This is not a universal policy for richer future search indexes.
"""
from __future__ import annotations
import argparse
from contextlib import closing
import hashlib
import html
import json
from pathlib import Path
import re
import sqlite3
import sys
import pulse_search_p18 as p18
import pulse_search_p11 as p11
import pulse_search_p16 as p16

VERSION='r2p19-static-index-live-intent-guard'
REPORT_HASH='170cc1618efac807ea47a294a1066aaa0ae1eaa632610f67438c368166633e7c'
INDEX_HASH='7a12e77fc5867fa27428023c30858f33488c5343c0e4a59a2d5455a721ef02ed'
REVIEW_HASH='832ffd9fee092245155054c038bac93ca272b14a6402d67fb57b47b3a2fb94ca'
SCORE={0:'no',1:'no',2:'partly',3:'yes'}
# Deliberately not gathered to select original 14 indexed pages. Still a tiny, non-random cohort.
NOVEL_QUERIES=(
 'How can I book an NHS blood test in England?',
 'What council tax band is my property in?',
 'How do I replace a lost UK passport?',
 'Can I register to vote in the UK without a permanent address?',
 'Where can I learn JavaScript programming?',
 'How does the SQL UNION operator work in SQLite?',
 'What time does London New Year\'s Eve 2026 start?',
 'Is Diwali on the Square London 2026 free to attend?',
 'What exhibitions in London are open this weekend?',
 'Are vegan hiking boots in stock near Manchester today?',
 'Which pharmacies in Bristol are open now?',
 'Is it raining in Glasgow right now?',
)
class Hold(ValueError):pass


def live_capability_needed(query):
    """Return a live-data capability, never claim no answer exists on the web.

    These signals require matching *current* providers/availability checks, absent
    from the research index. Avoid gating general date-specific events and guides.
    """
    if not isinstance(query,str) or not 1 <= len(query) <= 256:raise Hold('invalid_query')
    q=' '.join(query.casefold().split())
    now=r'(?:right now|currently|at the moment|today|this morning|this afternoon|tonight|now)'
    if (re.search(r'\b(?:weather|temperature|raining|rain|snowing|snowfall|wind speed|forecast)\b',q)
        and re.search(r'\b'+now+r'\b',q)):
        return 'current_weather'
    if (re.search(r'\b(?:open now|open right now|currently open|open tonight|open today|opening hours today)\b',q)
        and re.search(r'\b(?:restaurant|cafe|coffee shop|pharmac|chemist|shop|store|supermarket|clinic|dentist|pub|bar|business|place|places)\w*\b',q)):
        return 'live_business_hours'
    if ('in stock' in q or 'available for pickup' in q or 'available for collection' in q):
        return 'live_retail_inventory'
    # Physical goods sought for same-day local purchase, not generic guides on how to buy online.
    if (re.search(r'\b(?:where can i buy|where to buy|where can we buy|shops? selling|stores? selling|find .*? for sale)\b',q)
        and re.search(r'\b(?:today|right now|near me|nearby|this afternoon|tonight)\b',q)
        and re.search(r'\b(?:in [a-z][a-z-]+(?: [a-z][a-z-]+){0,2}|near me|nearby)\b',q)):
        return 'live_retail_inventory'
    return None


def load_bound(report,index,review):
    for f,expected in ((report,REPORT_HASH),(index,INDEX_HASH),(review,REVIEW_HASH)):
        if p18.sha256(p18.check_path(f))!=expected:raise Hold('owner_evidence_sha256_mismatch')
    source,binding=p18.validate(report,index)
    ratings=p18.load_json(p18.check_path(review))
    if (ratings.get('version')!=p18.VERSION or ratings.get('report_sha256')!=binding['report_sha256']
        or ratings.get('index_sha256')!=binding['index_sha256'] or len(ratings.get('questions',[]))!=19):
        raise Hold('unbound_human_review')
    for q,r in zip(source['questions'],ratings['questions']):
        if q['id']!=r.get('id'):raise Hold('review_question_order_mismatch')
        js=r.get('judgements')
        if not isinstance(js,list) or len(js)!=(1 if q['results'] else 0):raise Hold('review_result_count_mismatch')
        if js:
            hit=q['results'][0];j=js[0]
            if (j.get('url'),j.get('position'))!=(hit['url'],hit['position']):raise Hold('review_url_binding_mismatch')
            if type(j.get('grade')) is not int or j['grade'] not in SCORE or j.get('answer')!=SCORE[j['grade']]:
                raise Hold('invalid_grade_answer_binding')
    return source,ratings


def row_results(db,query,limit=5):
    return [h for h in p11.search_payload(db,query,limit=limit)['results'] if p16.year_compatible(query,h)]


def guard_static_index(query,hits):
    needs=live_capability_needed(query)
    if needs:
        return {'results':[], 'status':'LIVE_DATA_REQUIRED_NOT_VERIFIED_IN_STATIC_INDEX',
                'required_capability':needs, 'suppressed_unverified_hits':len(hits)}
    return {'results':hits,'status':'MATCHES_FOUND_NOT_VERIFIED_ANSWERS' if hits else 'NO_INDEXED_MATCH',
            'required_capability':None,'suppressed_unverified_hits':0}


def create_report(report,index,review):
    old,ratings=load_bound(report,index,review)
    scored=[];baseline={str(i):0 for i in range(4)};baseline['no_match']=0
    revised={str(i):0 for i in range(4)};revised['no_match']=0
    for q,r in zip(old['questions'],ratings['questions']):
        hits=q['results'];processed=guard_static_index(q['query'],hits)
        grade=r['judgements'][0]['grade'] if hits else None
        if grade is None:baseline['no_match']+=1
        else:baseline[str(grade)]+=1
        updated_grade=grade if processed['results'] else None
        if updated_grade is None:revised['no_match']+=1
        else:revised[str(updated_grade)]+=1
        scored.append({'id':q['id'],'query':q['query'],
            'baseline_top1':hits[0]['url'] if hits else None,'human_grade':grade,
            'candidate_top1':processed['results'][0]['url'] if processed['results'] else None,
            'candidate_known_grade':updated_grade,'status':processed['status'],
            'required_capability':processed['required_capability'],
            'suppressed_unverified_hits':processed['suppressed_unverified_hits']})
    if baseline!={'0':1,'1':0,'2':2,'3':13,'no_match':3}:
        raise Hold('accepted_r2p18_human_metrics_changed')
    if revised!={'0':0,'1':0,'2':2,'3':13,'no_match':4}:
        raise Hold('candidate_failed_pre_registered_regression_gate')
    if not next(x for x in scored if x['id']=='q15')['required_capability']=='live_retail_inventory':
        raise Hold('specific_existing_false_positive_not_suppressed')
    new=[]
    for i,q in enumerate(NOVEL_QUERIES,1):
        original=row_results(index,q)
        guarded=guard_static_index(q,original)
        new.append({'id':f'unseen_{i:02}','query':q,'baseline_results':len(original),
            'status':guarded['status'],'required_capability':guarded['required_capability'],
            'results':[{'position':j+1,'url':h['url'],'title':h['title'],'source_id':h['source_id'],
                        'human_grade':None,'verification':'HUMAN_REVIEW_REQUIRED'} for j,h in enumerate(guarded['results'])],
            'previously_unjudged':True})
    return {'version':VERSION,'status':'OFFLINE_ABSTENTION_REGRESSION_PASS_NOT_PRODUCTION_APPROVED',
      'binding':{'report_sha256':REPORT_HASH,'index_sha256':INDEX_HASH,'review_sha256':REVIEW_HASH},
      'indexed_pages':14,'sources':7,'prior':baseline,'candidate':revised,
      'top1_known_useful_retained':15,'known_direct_retained':13,
      'old_irrelevant_top1_suppressed':1,'novel_questions':len(new),
      'questions':scored,'unseen_queries':new,'paid_search_api_calls':0,'network_requests':0,
      'database_writes':0,'limitations':['Only a fixed 14-page research index with no live feeds',
        'Novel results have not been human reviewed',
        'No-match means no adequate indexed evidence, not no web answer',
        'Generic intent rules need much larger unseen-question evaluation before production use',
        'Future independently verified live-data sources require explicit capabilities, freshness and rights handling']}


def render(rep):
    esc=lambda x:html.escape(str(x),quote=True)
    buf=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>Pulse Search R2-P19 - Offline Relevance Review</title>',
         '<style>body{max-width:970px;padding:20px;margin:auto;font:16px system-ui;line-height:1.5;color:#17283a;background:#f4f6fa}section{background:#fff;padding:18px;border:1px solid #dce3ec;border-radius:12px;margin:18px 0}a{overflow-wrap:anywhere}.muted{color:#506176}span.tag{font-size:13px;background:#e2eafa;border-radius:4px;padding:3px}</style>',
         '<h1>R2-P19 — Static index / live-data gate</h1><p><strong>Experiment only.</strong> Baseline review is owner SHA-bound; this does not modify the live API or crawler. Novel questions need independent grading.</p>',
         '<p><b>Previously graded useful first hits retained: 15/15</b>; previously irrelevant first hit suppressed: 1/1. The dataset is too small for production conclusions.</p>',
         '<h2>12 fresh questions (NOT yet human-rated)</h2>']
    for q in rep['unseen_queries']:
        buf.append('<section><h3>'+esc(q['query'])+'</h3><p class="muted">'+esc(q['status'])+'</p>')
        if q['required_capability']:buf.append('<p>Live data required: '+esc(q['required_capability'])+'. Search elsewhere; not verifiable from this index.</p>')
        elif not q['results']:buf.append('<p>No indexed match. This is not proof the answer is unavailable.</p>')
        else:
            buf.append('<ol>')
            for hit in q['results']:
                buf.append('<li><a href="'+esc(hit['url'])+'" target="_blank" rel="noopener noreferrer">'+esc(hit['title'])+'</a> <span class="tag">NOT GRADED</span></li>')
            buf.append('</ol>')
        buf.append('</section>')
    return '\n'.join(buf+['</html>'])+'\n'


def run(report,index,review,out):
    target=Path(out)
    if target.exists():raise Hold('output_already_exists')
    before={str(x):p18.sha256(p18.check_path(x)) for x in (report,index,review)}
    result=create_report(report,index,review)
    after={str(x):p18.sha256(p18.check_path(x)) for x in (report,index,review)}
    if before!=after:raise Hold('original_input_changed_during_read_only_audit')
    target.mkdir(parents=True,exist_ok=False)
    (target/'abstention_report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (target/'unseen_question_review.html').write_text(render(result),encoding='utf-8')
    return result


def main(argv=None):
    ap=argparse.ArgumentParser()
    for n in ('report','index','review','out'):ap.add_argument('--'+n,required=True)
    a=ap.parse_args(argv)
    try:
        r=run(a.report,a.index,a.review,a.out)
        print(json.dumps({'status':r['status'],'prior':r['prior'],'candidate':r['candidate'],
          'known_useful_retained':r['top1_known_useful_retained'],
          'unseen_questions':r['novel_questions'],
          'report':str(Path(a.out)/'abstention_report.json'),
          'html':str(Path(a.out)/'unseen_question_review.html'),
          'paid_search_api_calls':0,'network_requests':0,'database_writes':0},indent=2))
        return 0
    except (Hold,p18.Hold,sqlite3.Error,ValueError,KeyError,OSError,TypeError) as ex:
        print('HOLD: '+str(ex),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
