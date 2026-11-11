#!/usr/bin/env python3
"""R2-P21: tightly scoped 3-origin research coverage expansion, clone-only.

The three exact seed URLs are ORIGINAL PUBLISHER research leads, not claimed
as autonomously discovered Pulse Search URLs. Requires separately explicit
opt-in for *live* retrieval. Not production or commercial publication rights.
"""
from __future__ import annotations
import argparse
from contextlib import closing
import hashlib
import html
import json
from pathlib import Path
import sqlite3
import sys

import pulse_search_engine as eng
import pulse_search_p11 as shadow
import pulse_search_p16 as p16
import pulse_search_p19 as p19

VERSION='0.21.0-independent-multiorigin-coverage-pilot'
OWNER_SHA='7a12e77fc5867fa27428023c30858f33488c5343c0e4a59a2d5455a721ef02ed'
REVIEW_SHA='e046bef682aa3e5f55ba1fdae79613e6a798d5c16cab4e6ead783c1af1ac51a6'
TARGETS=(
  {'source_id':'nhs_services','origin':'https://www.nhs.uk',
   'previous_paths':['/nhs-services/gps/how-to-register-with-a-gp-surgery/','/nhs-services/prescriptions/how-to-order-a-repeat-prescription/','/nhs-services/dentists/how-to-find-an-nhs-dentist/'],
   'url':'https://www.nhs.uk/tests-and-treatments/blood-tests/',
   'question':'How can I book an NHS blood test in England?'},
  {'source_id':'uk_services','origin':'https://www.gov.uk',
   'previous_paths':['/renew-adult-passport/renew','/register-to-vote','/apply-first-provisional-driving-licence'],
   'url':'https://www.gov.uk/council-tax-bands',
   'question':'What council tax band is my property in?'},
  {'source_id':'mdn_http','origin':'https://developer.mozilla.org',
   'previous_paths':['/en-US/docs/Web/HTTP'],
   'url':'https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Scripting/What_is_JavaScript',
   'question':'Where can I learn JavaScript programming?'},
)
CONTROL_QUESTIONS=('How can I register with a GP surgery?','What is HTTP?','Where can I register to vote?')
class Hold(ValueError):pass

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def readonly(db):
    p=Path(db).resolve(strict=True)
    if not p.is_file() or p.stat().st_size>2_000_000_000:raise Hold('missing_or_oversize_owner_index')
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=6)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c

def original_state(db,expected_sha=OWNER_SHA):
    p=Path(db).resolve(strict=True)
    initial=sha256(p)
    if initial!=expected_sha:raise Hold('owner_index_sha256_mismatch')
    with closing(readonly(p)) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise Hold('source_db_corrupt')
        pages=c.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
        fts=c.execute('SELECT COUNT(*) FROM page_fts').fetchone()[0]
        origins=c.execute('SELECT COUNT(DISTINCT source_id) FROM pages WHERE indexed=1').fetchone()[0]
        candidates=c.execute('SELECT COUNT(*) FROM sitemap_candidates').fetchone()[0]
        if (pages,fts,origins,candidates)!=(14,14,7,112):
            raise Hold('owner_index_structure_drift')
        sources={x['source_id']:dict(x) for x in c.execute('SELECT * FROM sources')}
        for item in TARGETS:
            source=sources.get(item['source_id'])
            if not source or source['origin']!=item['origin'] or source['approved']!=1 or source['enabled']!=1 or source['display_mode']!='metadata_only':
                raise Hold('unapproved_source_configuration')
            if json.loads(source['paths'])!=item['previous_paths']:
                raise Hold('previous_source_scope_changed')
            if not isinstance(source['rights_basis'],str) or len(source['rights_basis'])<20:
                raise Hold('source_rights_basis_missing')
            if eng.normal_url(item['url'])!=item['url'] or eng.origin(item['url'])!=source['origin']:
                raise Hold('noncanonical_or_cross_origin_seed')
            if c.execute('SELECT COUNT(*) FROM pages WHERE url=?',(item['url'],)).fetchone()[0]:
                raise Hold('target_already_indexed')
    return {'owner_index_sha256':initial,'baseline_pages':pages,'baseline_sources':origins,
            'sitemap_url_candidates':candidates,'source_policies':{k:sources[k] for k in (x['source_id'] for x in TARGETS)}}

def source_changes(state):
    # This adds one exact path per source, NEVER a whole-site wildcard.
    manifest=[]
    for item in TARGETS:
        s=state['source_policies'][item['source_id']]
        paths=json.loads(s['paths'])+[__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(item['url']).path]
        manifest.append({'source_id':item['source_id'],'origin':s['origin'],
          'allowed_paths':paths,'collection_approved':True,'display_mode':'metadata_only',
          'rights_basis':s['rights_basis']+'; R2-P21 three exact new paths: operator-approved bounded internal metadata technical pilot ONLY, no commercial reuse.'})
    eng.validate_sources(manifest)
    return manifest

def verify_review(review):
    p=Path(review).resolve(strict=True)
    if sha256(p)!=REVIEW_SHA:raise Hold('human_review_sha256_mismatch')
    j=json.loads(p.read_text(encoding='utf-8'))
    if (j.get('version')!='r2p20-unseen-review-v1' or j.get('source_report_sha256')!='5489eff6db988fefc5babd7ff5cfee8cfdb0e0561a293272452afcb7c847e53f'
        or len(j.get('questions',[]))!=12):raise Hold('human_review_data_mismatch')
    expected={'unseen_01':1,'unseen_02':0,'unseen_03':3,'unseen_04':2,'unseen_05':3,'unseen_06':2,'unseen_07':2,'unseen_08':2,'unseen_09':1}
    for x in j['questions']:
        if x['id'] in expected and x.get('grade')!=expected[x['id']]:raise Hold('human_grade_mismatch')
    return j

def page_map(db):
    with closing(readonly(db)) as c:
        return {x['url']:dict(x) for x in c.execute('SELECT url,source_id,title,content_sha256,indexed FROM pages ORDER BY url')}

def report_html(result):
    out=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P21 Research</title>',
       '<style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:1rem;line-height:1.5}section{margin:1rem 0;border:1px solid #bbb;border-radius:10px;padding:1rem}a{overflow-wrap:anywhere}</style>',
       '<h1>Pulse Search — Three original-publisher source expansion (R2-P21)</h1>',
       '<p><strong>Not production.</strong> Pages, if indexed, remain research-only metadata. No answer or display rights are inferred.</p>',
       '<p>Status: '+html.escape(result['status'])+'. Original index pages: 14, clone after: '+str(result['indexed_pages_after'])+'</p>']
    for q in result['queries']:
        out.append('<section><h2>'+html.escape(q['query'])+'</h2><p>'+html.escape(q['coverage_status'])+'</p>')
        if q['results']:
            out.append('<ol>')
            for h in q['results']:
                out.append('<li><a rel="noopener noreferrer" href="'+html.escape(h['url'],quote=True)+'">'+html.escape(h['title'])+'</a> <small>ungraded</small></li>')
            out.append('</ol>')
        else:out.append('<p>No indexed match (not proof of absence online).</p>')
        out.append('</section>')
    return '\n'.join(out+['</html>'])+'\n'

def execute(index,review,out,allow_live=False,expected_sha=OWNER_SHA):
    target=Path(out).resolve()
    if target.exists():raise Hold('output_directory_exists')
    original=Path(index).resolve(strict=True)
    state=original_state(original,expected_sha)
    verify_review(review)
    policies=source_changes(state)
    before=page_map(original)
    target.mkdir(parents=True)
    clone=target/'expanded_research_index.sqlite'
    p16.copy_db_readonly(original,clone)
    new_urls=[i['url'] for i in TARGETS]
    crawl=None
    if allow_live:
        with eng.dbopen(clone) as conn:
            for s in policies:
                conn.execute('UPDATE sources SET paths=?,rights_basis=? WHERE source_id=? AND enabled=1 AND approved=1',
                             (json.dumps(s['allowed_paths']),s['rights_basis'],s['source_id']))
            for s in policies:
                row=conn.execute('SELECT * FROM sources WHERE source_id=?',(s['source_id'],)).fetchone()
                if row['paths']!=json.dumps(s['allowed_paths']):raise Hold('clone_scope_extension_failed')
        cfg=target/'limited_new_path_source_config.json'
        cfg.write_text(json.dumps(policies,indent=2)+'\n',encoding='utf-8')
        crawl=eng.crawl(str(clone),str(cfg),new_urls,max_pages=3,max_depth=0,min_delay=2.0,
                       sitemaps=False,scheduled_urls=new_urls)
    after=page_map(clone)
    if any(url not in after or after[url]!=p for url,p in before.items()):
        raise Hold('previously_indexed_pages_changed')
    new=[{'url':url,'title':after[url]['title']} for url in new_urls if url in after and after[url]['indexed']==1]
    if sha256(original)!=state['owner_index_sha256']:raise Hold('accepted_owner_database_changed')
    with closing(readonly(clone)) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise Hold('clone_integrity_failure')
        n=c.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
        f=c.execute('SELECT COUNT(*) FROM page_fts').fetchone()[0]
        if f!=n or n!=14+len(new):raise Hold('clone_index_mismatch')
    queries=[]
    for q in [t['question'] for t in TARGETS]+list(CONTROL_QUESTIONS):
        raw=shadow.search_payload(clone,q,limit=3)
        queries.append({'query':q,'coverage_status':raw['coverage_status'],'results':[
            {k:h[k] for k in ('url','title','position')} for h in raw['results']],
            'human_grade':'PENDING_FRESH_REVIEW'})
    status=('RESEARCH_CLONE_ALL_THREE_INDEXED_NOT_PRODUCTION' if len(new)==3 else
            'LIVE_PARTIAL_OR_NO_NEW_PAGES_HOLD' if allow_live else 'READ_ONLY_PREFLIGHT_PASS_LIVE_PENDING')
    report={'version':VERSION,'status':status,'original_owner_index_sha256':state['owner_index_sha256'],
           'owner_review_sha256':REVIEW_SHA,'previous_indexed_pages':14,'indexed_pages_after':n,
           'new_indexed_pages':new,'requested_exact_url_seeds':new_urls,
           'seed_provenance':'human_independently_resolved_original_publishers; NOT Pulse sitemap-discovered',
           'source_scope_extensions':'ONLY_THREE_EXACT_URL_PATHS_IN_DISPOSABLE_CLONE' if allow_live else 'NOT_APPLIED',
           'original_db_writes':0,'paid_search_provider_calls':0,
           'network_requests':crawl['fetch_requests'] if crawl else 0,'crawl_outcomes':crawl['outcomes'] if crawl else {},
           'queries':queries,'limitations':['Live index research is not a web-scale search benchmark',
                   'Human judgement on new rankings is required',
                   'Source publisher licences and commercial reproduction rights are NOT granted',
                   'Three hand-researched exact URL seeds do not demonstrate autonomous discovery']}
    (target/'coverage_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (target/'search_review.html').write_text(report_html(report),encoding='utf-8')
    return report

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--owner-index',required=True)
    ap.add_argument('--review',required=True)
    ap.add_argument('--out',required=True)
    ap.add_argument('--live',action='store_true')
    a=ap.parse_args(argv)
    try:
        r=execute(a.owner_index,a.review,a.out,a.live)
        print(json.dumps({'status':r['status'],'indexed_pages_after':r['indexed_pages_after'],
            'new_indexed_pages':r['new_indexed_pages'],'network_requests':r['network_requests'],
            'paid_search_provider_calls':0,'report':str(Path(a.out)/'coverage_report.json'),
            'review_html':str(Path(a.out)/'search_review.html')},indent=2))
        return 0 if not a.live or len(r['new_indexed_pages'])==3 else 2
    except (Hold,p16.Hold,eng.Hold,ValueError,KeyError,OSError,sqlite3.Error,TypeError) as exc:
        print('HOLD: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
