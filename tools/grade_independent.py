#!/usr/bin/env python3
"""Audit frozen Pulse Search replay and attributed independent grades (stdlib/read-only).

Does NOT invoke Pulse Search, invent relevance labels or claim factual certification.
Replay rows: probe_id,engine,rank,title,url,source_id,filter_status
Grade rows: probe_id,engine,rank,relevance,reviewer_id,source_verified,exclusion_violation,edition_correct
Engine A/B mappings remain undisclosed to reviewers until grading is complete.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def csv_rows(path):
    if not path:
        return []
    with open(path, newline='', encoding='utf-8-sig') as fh:
        return list(csv.DictReader(fh))


def required_fields(rows, required, name):
    if rows and not required.issubset(rows[0]):
        raise ValueError(f'{name}: missing {sorted(required - set(rows[0]))}')


def assess(frozen, results, grades):
    required_fields(frozen, {'probe_id', 'question', 'kind'}, 'frozen')
    required_fields(results, {'probe_id', 'engine', 'rank', 'title', 'url'}, 'results')
    required_fields(grades, {'probe_id', 'engine', 'rank', 'relevance',
                             'reviewer_id', 'source_verified'}, 'grades')
    queries = {q['probe_id']: q for q in frozen}
    if len(frozen) != 54 or len(queries) != 54:
        raise ValueError('frozen list must contain 54 unique queries')
    candidates = defaultdict(dict)
    observed_engines = set()
    for r in results:
        p, e = r['probe_id'], r['engine']
        if p not in queries or e not in ('A', 'B'):
            raise ValueError(f'unknown probe or unblinded engine: {p}/{e}')
        k = int(r['rank'])
        if not 1 <= k <= 10:
            raise ValueError(f'invalid rank: {p}/{e}/{k}')
        if k in candidates[p, e]:
            raise ValueError(f'duplicate rank: {p}/{e}/{k}')
        candidates[p, e][k] = r
        observed_engines.add(e)
    for (p, e), ranks in candidates.items():
        if set(ranks) != set(range(1, max(ranks) + 1)):
            raise ValueError(f'non-contiguous candidate ranks: {p}/{e}')
    labels = defaultdict(dict)
    verified = 0
    for r in grades:
        p, e = r['probe_id'], r['engine']
        if p not in queries or e not in ('A', 'B'):
            raise ValueError(f'unknown grade key: {p}/{e}')
        k = int(r['rank'])
        if k not in candidates[p, e]:
            raise ValueError(f'grade without candidate: {p}/{e}/{k}')
        if k in labels[p, e]:
            raise ValueError(f'duplicate grade: {p}/{e}/{k}')
        relevance = r['relevance'].strip()
        if relevance not in ('0', '1', '2', '3'):
            raise ValueError(f'invalid relevance label: {p}/{e}/{k}')
        if not r['reviewer_id'].strip():
            raise ValueError(f'unsigned grade: {p}/{e}/{k}')
        if r['source_verified'].strip().upper() not in ('YES', 'NO'):
            raise ValueError(f'unresolved source verification: {p}/{e}/{k}')
        verified += int(r['source_verified'].strip().upper() == 'YES')
        labels[p, e][k] = int(relevance)
    scored = {}
    for e in sorted(observed_engines):
        completed = []
        for p, q in queries.items():
            ranks = candidates.get((p, e))
            if not ranks or q['kind'] == 'no_result':
                continue
            top = [k for k in sorted(ranks) if k <= 5]
            if not top or any(k not in labels[p, e] for k in top):
                continue
            good = [labels[p, e][k] >= 2 for k in top]
            completed.append((
                int(good[0]),
                sum(good) / 5.0,
                next((1.0 / (i + 1) for i, yes in enumerate(good) if yes), 0.0),
                sum(not yes for yes in good) / 5.0,
            ))
        def avg(i):
            return round(sum(row[i] for row in completed) / len(completed), 4) if completed else None
        scored[e] = {
            'replayed_queries_with_candidate_rows': sum(bool(candidates.get((p, e))) for p in queries),
            'queries_with_signed_top5_labels': len(completed),
            'precision_at_1_signed_subset': avg(0),
            'precision_at_5_signed_subset': avg(1),
            'mrr_at_5_signed_subset': avg(2),
            'noise_at_5_signed_subset': avg(3),
            'scope_warning': 'SIGNED_SUBSET_ONLY; NEVER EQUATE WITH 54-CASE ACCEPTANCE',
        }
    return {
        'frozen_query_count': len(queries),
        'historic_labels_are_automated_not_human': True,
        'candidate_rows_loaded': len(results),
        'blind_engines_seen': sorted(observed_engines),
        'signed_candidate_judgements': len(grades),
        'source_verified_judgements': verified,
        'negative_abstention': 'HOLD_REQUIRES_EXPLICIT_EMPTY_RESPONSE_RECEIPTS',
        'recall_at_5': 'HOLD_REQUIRES_KNOWN_COMPLETE_RELEVANCE_SET',
        'by_engine': scored,
        'overall_decision': 'HOLD_PENDING_FULL_REPLAY_AND_INDEPENDENT_EVIDENCE',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--frozen', required=True)
    parser.add_argument('--results', help='Actual A/B replay candidate CSV, never invented')
    parser.add_argument('--grades', help='Independent signed reviewer grades CSV')
    parser.add_argument('--output', help='New JSON report path; no overwrites')
    args = parser.parse_args()
    result = assess(csv_rows(args.frozen), csv_rows(args.results), csv_rows(args.grades))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        path = Path(args.output)
        if path.exists():
            parser.error('refusing to overwrite evidence')
        path.write_text(payload, encoding='utf-8')
    print(payload, end='')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        print('INVALID_EVIDENCE: ' + str(exc), file=sys.stderr)
        sys.exit(2)
