#!/usr/bin/env python3
"""R2-P18: offline, human-reviewed top-1 quality gate for accepted R2-P17 index.
No network access, no mutation of accepted reports/index; user ratings bind to exact bytes.
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
from urllib.parse import urlsplit

VERSION='r2p18-human-top1-review'
EXPECTED={'pages':14,'sources':7,'questions':19,'candidates':112}
ACCEPTED_STATUS='CROSS_SOURCE_INTERNAL_RESEARCH_INDEX_NOT_PRODUCTION'
ALLOWED_ANSWER={0:'no',1:'no',2:'partly',3:'yes'}
class Hold(ValueError): pass

def sha256(p):
    d=hashlib.sha256()
    with open(p,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):d.update(block)
    return d.hexdigest()

def load_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def check_path(p):
    f=Path(p)
    if not f.is_file() or f.is_symlink() or f.stat().st_size > 50_000_000:raise Hold('missing_oversized_or_symlink_input')
    return f.resolve(strict=True)

def ro_db(p):
    path=check_path(p)
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c

def validate(report_path,db_path):
    p=check_path(report_path);db=check_path(db_path)
    report=load_json(p)
    if report.get('version')!='0.17.0-r2p17-source-safe-research-index' or report.get('status')!=ACCEPTED_STATUS:
        raise Hold('not_accepted_r2p17_report')
    ci=report.get('combined_index',{})
    if ci.get('indexed_pages')!=14 or ci.get('sources')!=7 or ci.get('fts_rows')!=14 or ci.get('sitemap_leads_retained')!=112:
        raise Hold('unexpected_report_index_scope')
    if (report.get('query_count')!=19 or report.get('known_direct_answer_top1')!=9
        or report.get('new_top1_require_human_review')!=5 or report.get('no_indexed_match_questions')!=3
        or report.get('network_requests')!=0 or report.get('paid_search_provider_calls')!=0
        or report.get('owner_database_writes')!=0):
        raise Hold('unexpected_r2p17_acceptance_metrics')
    if len(report.get('skipped_origin_policy_conflicts',[]))!=1 or len(report.get('questions',[]))!=19:
        raise Hold('missing_scope_conflict_or_questions')
    with closing(ro_db(db)) as c:
        if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise Hold('index_corrupt')
        if c.execute('SELECT count(*) FROM pages WHERE indexed=1').fetchone()[0]!=14:raise Hold('indexed_pages_changed')
        if c.execute('SELECT count(*) FROM page_fts').fetchone()[0]!=14:raise Hold('fts_count_changed')
        if c.execute('SELECT count(DISTINCT source_id) FROM pages WHERE indexed=1').fetchone()[0]!=7:raise Hold('source_count_changed')
        if c.execute('SELECT count(*) FROM sitemap_candidates').fetchone()[0]!=112:raise Hold('candidate_count_changed')
        sources=c.execute('SELECT approved,enabled,display_mode,rights_basis FROM sources').fetchall()
        if len(sources)!=7 or any(s['approved']!=1 or s['enabled']!=1 or s['display_mode']!='metadata_only' or len(s['rights_basis'])<20 for s in sources):
            raise Hold('source_policy_changed')
        lookup={r['url']:dict(r) for r in c.execute('SELECT url,title,source_id FROM pages WHERE indexed=1')}
        qids=[];direct=0;novel=0;unmatched=0
        for q in report['questions']:
            qid=q.get('id');query=q.get('query')
            if not isinstance(qid,str) or not re.fullmatch(r'(q\d{2}|additional_[1-4])',qid) or qid in qids:raise Hold('bad_question_ids')
            qids.append(qid)
            if not isinstance(query,str) or not 5<=len(query)<=250:raise Hold('invalid_question')
            rows=q.get('results')
            if not isinstance(rows,list) or len(rows)>5:raise Hold('bad_result_count')
            if not rows:unmatched+=1
            if rows and q.get('top1_known_direct_answer'):direct+=1
            if rows and q.get('new_top1_needs_review'):novel+=1
            if q.get('coverage_status')!=('INDEXED_MATCHES_UNVERIFIED' if rows else 'NO_INDEXED_MATCH'):
                raise Hold('coverage_flag_inconsistent')
            if len({h.get('url') for h in rows})!=len(rows):raise Hold('duplicate_result_url')
            last_position=0
            for i,h in enumerate(rows,1):
                url=h.get('url');f=lookup.get(url)
                if (not isinstance(url,str) or not f or urlsplit(url).scheme!='https'
                    or urlsplit(url).username or urlsplit(url).password or len(url)>1500
                    or type(h.get('position')) is not int or not 1<=h['position']<=5 or h['position']<=last_position
                    or h.get('title')!=f['title'] or h.get('source_id')!=f['source_id']):
                    raise Hold('result_not_bound_to_index')
                last_position=h['position']
                grade=h.get('previous_human_grade');answer=h.get('previous_human_answer')
                if grade is None:
                    if answer is not None or h.get('verification')!='HUMAN_REVIEW_REQUIRED':raise Hold('previous_grade_inconsistent')
                elif type(grade)!=int or grade not in ALLOWED_ANSWER or answer!=ALLOWED_ANSWER[grade] or h.get('verification')!='PREVIOUSLY_HUMAN_GRADED':
                    raise Hold('previous_grade_inconsistent')
            if bool(rows and rows[0]['previous_human_answer']=='yes')!=q.get('top1_known_direct_answer'):
                raise Hold('known_direct_flag_inconsistent')
            if bool(rows and rows[0]['previous_human_grade'] is None)!=q.get('new_top1_needs_review'):
                raise Hold('review_flag_inconsistent')
        if qids!=[f'q{i:02}' for i in range(1,16)]+[f'additional_{i}' for i in range(1,5)]:raise Hold('question_sequence_invalid')
        if (direct,novel,unmatched)!=(9,5,3):raise Hold('top1_metric_mismatch')
    return report,{'report_sha256':sha256(p),'index_sha256':sha256(db),**EXPECTED}

def render(report,bind):
    esc=lambda x:html.escape(str(x),quote=True)
    x=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>Pulse Search R2-P18 — 19-query human assessment</title>',
       '<style>body{font:16px system-ui,sans-serif;line-height:1.5;max-width:950px;margin:25px auto;padding:0 18px;background:#f4f7fa;color:#17263a}header,section{background:white;border:1px solid #d8e0eb;border-radius:12px;padding:18px;margin-bottom:16px}h2{font-size:21px}a{overflow-wrap:anywhere;color:#1460a7}select{display:block;width:min(460px,100%);padding:10px;margin:7px 0 14px}label{font-weight:600}small,.muted{color:#506177}.sticky{position:sticky;bottom:0;background:#173b5e;padding:14px;color:white;border-radius:9px}button{font:inherit;border:0;border-radius:6px;background:#d6edff;color:#163c5e;padding:10px 18px;cursor:pointer}.flag{border-left:4px solid #dd9b31;padding:8px;background:#fff6e9}.zero{border-left:4px solid #3c8f75;padding:8px;background:#effaf5}</style>',
       '<header><h1>Pulse Search — Human quality review (R2-P18)</h1><p><strong>Research only.</strong> Evaluate the <strong>first returned page</strong> for each of the 16 queries with a result. Three queries have no indexed match and need no grade. Ratings are deliberately not prefilled.</p><p>Open a publisher link and judge whether the actual webpage answers the exact question. A related subject is not automatically an answer. All pages and review data remain on your computer until you choose to upload the exported JSON.</p><p class="muted">14 indexed pages · 7 sources · 19 questions · zero external API calls</p></header>']
    for q in report['questions']:
        x.append('<section class="question" data-id="'+esc(q['id'])+'"><h2>'+esc(q['query'])+'</h2>')
        if not q['results']:
            x.append('<p class="zero">NO INDEXED MATCH — the page may still exist elsewhere on the internet.</p>')
        else:
            h=q['results'][0]
            x.append('<article class="top" data-url="'+esc(h['url'])+'" data-position="'+str(h['position'])+'">'
                     '<p><strong>First result:</strong> <a href="'+esc(h['url'])+'" target="_blank" rel="noopener noreferrer">'+esc(h['title'])+'</a></p>'
                     '<p class="muted">Source: '+esc(h['source_id'])+'</p>')
            if h['previous_human_grade'] is not None:
                x.append('<p class="muted">Earlier grade on this URL for this question: '+str(h['previous_human_grade'])+'/3. Please reassess this ranking independently.</p>')
            else:x.append('<p class="flag">NEW FIRST RESULT — independent review required.</p>')
            x.append('<label>How useful is this first result for the question?<select class="grade" required><option value="">Select grade</option><option value="0">0 — Irrelevant</option><option value="1">1 — Related, does not answer</option><option value="2">2 — Useful but incomplete</option><option value="3">3 — Directly answers question</option></select></label>'
                     '<label>Answer assessment<select class="answer" required><option value="">Select answer</option><option value="no">No</option><option value="partly">Partly</option><option value="yes">Yes</option></select></label></article>')
            if len(q['results'])>1:
                x.append('<details><summary>'+str(len(q['results'])-1)+' other results (not graded in this pilot)</summary><ol>')
                for alt in q['results'][1:]:
                    x.append('<li><a href="'+esc(alt['url'])+'" rel="noopener noreferrer" target="_blank">'+esc(alt['title'])+'</a></li>')
                x.append('</ol></details>')
        x.append('</section>')
    # Fingerprint bind is only hex/numbers; serialization via json.dumps still safe.
    script="""const binding=__BIND__;function saveReview(){let missing=0,errors=0;const questions=[];document.querySelectorAll('.question').forEach(q=>{const top=q.querySelector('.top'), judgements=[];if(top){const g=top.querySelector('.grade').value,a=top.querySelector('.answer').value;if(g===''||a==='')missing++;else if(({0:'no',1:'no',2:'partly',3:'yes'})[g]!==a)errors++;judgements.push({url:top.dataset.url,position:Number(top.dataset.position),grade:g===''?null:Number(g),answer:a||null});}questions.push({id:q.dataset.id,judgements});});const status=document.getElementById('status');if(missing||errors){status.textContent=`Not exported: ${missing} incomplete answers, ${errors} grade/answer contradictions.`;return;}const data={version:'r2p18-human-top1-review',report_sha256:binding.report_sha256,index_sha256:binding.index_sha256,questions};const blob=new Blob([JSON.stringify(data,null,2)+'\\n'],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='Pulse_Search_R2P18_Reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);status.textContent='Reviewed JSON exported. Upload it in ChatGPT for independent scoring.';}""".replace('__BIND__',json.dumps(bind,separators=(',',':')))
    x.append('<div class="sticky"><button onclick="saveReview()">Export reviewed JSON</button> <span id="status">Grade all 16 first results to enable export.</span></div><script>'+script+'</script></html>')
    return '\n'.join(x)+'\n'

def prepare(report,db,out):
    r,b=validate(report,db)
    o=Path(out)
    if o.exists():raise Hold('output_directory_exists')
    o.mkdir(parents=True,exist_ok=False)
    (o/'review.html').write_text(render(r,b),encoding='utf-8')
    (o/'review_manifest.json').write_text(json.dumps({'version':VERSION,**b,'pending_first_results':16,'previously_ungraded_first_results':5,'no_match_questions':3},indent=2)+'\n',encoding='utf-8')
    return {'status':'HUMAN_TOP1_REVIEW_REQUIRED','graded_first_results_pending':16,'new_first_results_pending':5,'no_indexed_match_questions':3,'report_sha256':b['report_sha256'],'index_sha256':b['index_sha256'],'review_html':str(o/'review.html'),'network_requests':0,'paid_provider_calls':0}

def score(report,db,review,out):
    r,b=validate(report,db)
    human=load_json(check_path(review))
    if human.get('version')!=VERSION or human.get('report_sha256')!=b['report_sha256'] or human.get('index_sha256')!=b['index_sha256']:
        raise Hold('review_not_bound_to_accepted_report_and_index')
    qreviews=human.get('questions')
    if not isinstance(qreviews,list) or len(qreviews)!=19:raise Hold('review_question_count_invalid')
    counters={'direct':0,'partial':0,'related':0,'irrelevant':0,'no_match':0}
    new_grades=[]
    for original,rev in zip(r['questions'],qreviews):
        if rev.get('id')!=original['id'] or not isinstance(rev.get('judgements'),list):raise Hold('review_question_order_changed')
        if not original['results']:
            if rev['judgements']:raise Hold('ratings_supplied_for_no_match_query')
            counters['no_match']+=1;continue
        if len(rev['judgements'])!=1:raise Hold('missing_or_extra_first_result_judgement')
        j=rev['judgements'][0];first=original['results'][0]
        if j.get('url')!=first['url'] or j.get('position')!=first['position']:raise Hold('judged_result_url_or_position_changed')
        grade=j.get('grade');ans=j.get('answer')
        if type(grade)!=int or grade not in ALLOWED_ANSWER or ans!=ALLOWED_ANSWER[grade]:raise Hold('grade_answer_contradiction')
        counters[{3:'direct',2:'partial',1:'related',0:'irrelevant'}[grade]]+=1
        if first['previous_human_grade'] is None:new_grades.append({'id':original['id'],'query':original['query'],'grade':grade,'answer':ans,'url':j['url']})
    if sum(counters.values())!=19 or len(new_grades)!=5:raise Hold('review_scope_changed')
    data={'status':'R2P18_HUMAN_TOP1_SCORED_RESEARCH_ONLY','question_count':19,'top1_scores':counters,'newly_graded_top1':new_grades,'report_sha256':b['report_sha256'],'index_sha256':b['index_sha256'],'paid_provider_calls':0,'network_requests':0,'limitations':['Only 14 preselected pages and 19 pilot questions, not open-web quality estimate','Human grading does not grant reproduction or commercial rights','No-match does not imply no answer on public web']}
    o=Path(out)
    if o.exists():raise Hold('scored_output_exists')
    o.mkdir(parents=True,exist_ok=False)
    (o/'scored_report.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return data

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--report',required=True);p.add_argument('--db',required=True);p.add_argument('--out',required=True)
    p.add_argument('--score',help='Reviewed JSON exported from review.html')
    a=p.parse_args()
    try:
        result=score(a.report,a.db,a.score,a.out) if a.score else prepare(a.report,a.db,a.out)
        print(json.dumps(result,indent=2,ensure_ascii=False));return 0
    except (Hold,OSError,ValueError,KeyError,TypeError,sqlite3.Error) as ex:
        print('HOLD: '+str(ex),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
