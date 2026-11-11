import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pulse_search_p18 as p

class TestP18(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.db=self.root/'index.sqlite';self.report_path=self.root/'combined_report.json'
        c=sqlite3.connect(self.db)
        c.executescript('''CREATE TABLE sources (source_id TEXT, approved INTEGER, enabled INTEGER, display_mode TEXT, rights_basis TEXT);
             CREATE TABLE pages (url TEXT, title TEXT, source_id TEXT, indexed INTEGER);
             CREATE TABLE page_fts (title TEXT);
             CREATE TABLE sitemap_candidates (url TEXT);''')
        pages=[]
        for i in range(7):
            sid=f'source{i}';c.execute('INSERT INTO sources VALUES(?,?,?,?,?)',(sid,1,1,'metadata_only','Internal research rights reviewed and scoped only.'))
            for j in range(2):
                url=f'https://www.example{i}.org/research/{j}'
                title=f'Publisher Event {i} {j}'
                c.execute('INSERT INTO pages VALUES(?,?,?,1)',(url,title,sid))
                c.execute('INSERT INTO page_fts VALUES(?)',(title,))
                pages.append({'url':url,'title':title,'source_id':sid})
        c.executemany('INSERT INTO sitemap_candidates VALUES(?)',[(f'https://sample.org/event/{i}',) for i in range(112)])
        c.commit();c.close()
        no={2,9,16};qs=[]
        statuses=[3]*9+[1,2]+[None]*5
        count=0
        for i in range(19):
            qid=f'q{i+1:02}' if i<15 else f'additional_{i-14}'
            hits=[]
            if i not in no:
                page=pages[i%14];g=statuses[count];count+=1
                hits=[dict(page,position=(2 if i==1 else 1),previous_human_grade=g,
                           previous_human_answer=p.ALLOWED_ANSWER[g] if g is not None else None,
                           verification='PREVIOUSLY_HUMAN_GRADED' if g is not None else 'HUMAN_REVIEW_REQUIRED')]
            qs.append({'id':qid,'query':f'Search question number {i+1} about accepted research pages',
                       'results':hits, 'coverage_status':'INDEXED_MATCHES_UNVERIFIED' if hits else 'NO_INDEXED_MATCH',
                       'top1_known_direct_answer':bool(hits and hits[0]['previous_human_answer']=='yes'),
                       'new_top1_needs_review':bool(hits and hits[0]['previous_human_grade'] is None)})
        report={'version':'0.17.0-r2p17-source-safe-research-index','status':p.ACCEPTED_STATUS,
                'combined_index':{'indexed_pages':14,'sources':7,'fts_rows':14,'sitemap_leads_retained':112},
                'query_count':19,'known_direct_answer_top1':9,'new_top1_require_human_review':5,
                'no_indexed_match_questions':3,'network_requests':0,'paid_search_provider_calls':0,
                'owner_database_writes':0,'skipped_origin_policy_conflicts':[{'origin':'x','reason':'test'}],
                'questions':qs}
        self.report_path.write_text(json.dumps(report),encoding='utf-8')
        self.report=report
    def review_data(self):
        r,b=p.validate(self.report_path,self.db)
        return {'version':p.VERSION,'report_sha256':b['report_sha256'],'index_sha256':b['index_sha256'],
                'questions':[{'id':q['id'],'judgements':([{'url':q['results'][0]['url'],'position':q['results'][0]['position'],'grade':3,'answer':'yes'}] if q['results'] else [])} for q in r['questions']]}
    def test_validate(self):
        r,b=p.validate(self.report_path,self.db)
        self.assertEqual(b['questions'],19)
        self.assertEqual(len(r['questions']),19)
    def test_prepare(self):
        result=p.prepare(self.report_path,self.db,self.root/'review')
        self.assertEqual(result['graded_first_results_pending'],16)
        text=(self.root/'review/review.html').read_text()
        self.assertEqual(text.count('<select class="grade"'),16)
        self.assertIn('data-position="2"',text)
        self.assertNotIn('http://',text)
    def test_score(self):
        data=self.review_data();review=self.root/'reviewed.json';review.write_text(json.dumps(data))
        score=p.score(self.report_path,self.db,review,self.root/'scored')
        self.assertEqual(score['top1_scores'],{'direct':16,'partial':0,'related':0,'irrelevant':0,'no_match':3})
        self.assertEqual(len(score['newly_graded_top1']),5)
    def test_reject_report_change(self):
        doc=self.review_data();self.report['questions'][0]['query']='Altered query text';self.report_path.write_text(json.dumps(self.report))
        review=self.root/'reviewed.json';review.write_text(json.dumps(doc))
        with self.assertRaisesRegex(p.Hold,'not_bound'):p.score(self.report_path,self.db,review,self.root/'scored')
    def test_reject_index_change(self):
        doc=self.review_data();review=self.root/'reviewed.json';review.write_text(json.dumps(doc))
        c=sqlite3.connect(self.db);c.execute('UPDATE pages SET title=? WHERE url=?',('Changed',self.report['questions'][0]['results'][0]['url']));c.commit();c.close()
        with self.assertRaises(p.Hold):p.score(self.report_path,self.db,review,self.root/'scored')
    def test_reject_grade_answer_conflict(self):
        doc=self.review_data();doc['questions'][0]['judgements'][0]['grade']=0
        review=self.root/'reviewed.json';review.write_text(json.dumps(doc))
        with self.assertRaisesRegex(p.Hold,'contradiction'):p.score(self.report_path,self.db,review,self.root/'scored')
    def test_reject_wrong_url(self):
        doc=self.review_data();doc['questions'][0]['judgements'][0]['url']='https://www.fake.org/'
        review=self.root/'reviewed.json';review.write_text(json.dumps(doc))
        with self.assertRaisesRegex(p.Hold,'url_or_position'):p.score(self.report_path,self.db,review,self.root/'scored')
    def test_reject_wrong_position(self):
        doc=self.review_data();doc['questions'][1]['judgements'][0]['position']=1
        review=self.root/'reviewed.json';review.write_text(json.dumps(doc))
        with self.assertRaisesRegex(p.Hold,'url_or_position'):p.score(self.report_path,self.db,review,self.root/'scored')
    def test_reject_unrated_top1(self):
        doc=self.review_data();doc['questions'][0]['judgements']=[]
        review=self.root/'reviewed.json';review.write_text(json.dumps(doc))
        with self.assertRaisesRegex(p.Hold,'missing_or_extra'):p.score(self.report_path,self.db,review,self.root/'scored')
    def test_reject_fake_no_match_judgement(self):
        doc=self.review_data();doc['questions'][2]['judgements']=[{'grade':3,'answer':'yes'}]
        review=self.root/'reviewed.json';review.write_text(json.dumps(doc))
        with self.assertRaisesRegex(p.Hold,'no_match_query'):p.score(self.report_path,self.db,review,self.root/'scored')
    def test_reject_bad_report_metric(self):
        self.report['paid_search_provider_calls']=1;self.report_path.write_text(json.dumps(self.report))
        with self.assertRaisesRegex(p.Hold,'metrics'):p.validate(self.report_path,self.db)
    def test_reject_inconsistent_report_title(self):
        self.report['questions'][0]['results'][0]['title']='Forged';self.report_path.write_text(json.dumps(self.report))
        with self.assertRaisesRegex(p.Hold,'result_not_bound'):p.validate(self.report_path,self.db)
    def test_reject_non_https_result(self):
        self.report['questions'][0]['results'][0]['url']='javascript:alert(1)';self.report_path.write_text(json.dumps(self.report))
        with self.assertRaisesRegex(p.Hold,'result_not_bound'):p.validate(self.report_path,self.db)
    def test_reject_existing_destination(self):
        self.root.joinpath('review').mkdir()
        with self.assertRaisesRegex(p.Hold,'exists'):p.prepare(self.report_path,self.db,self.root/'review')
    def test_render_html_escape(self):
        self.report['questions'][0]['query']='<svg onload=alert(1)>'
        raw=p.render(self.report,{'report_sha256':'a'*64,'index_sha256':'b'*64})
        self.assertIn('&lt;svg',raw)
        self.assertNotIn('<svg onload',raw)
    def test_refuse_symlink(self):
        shortcut=self.root/'reportlink.json';shortcut.symlink_to(self.report_path)
        with self.assertRaisesRegex(p.Hold,'symlink'):p.validate(shortcut,self.db)

if __name__=='__main__':unittest.main()
