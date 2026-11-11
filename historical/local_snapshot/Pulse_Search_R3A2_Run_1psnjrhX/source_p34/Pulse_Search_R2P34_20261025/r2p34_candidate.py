#!/usr/bin/env python3
"""R2-P34 limited, generic syntax fixes layered on independently evaluated P33.

Read-only, metadata retrieval. Not a fact-answering system. Never imports test
expectations, maps questions to URLs, or makes network calls. Do not deploy.
"""
from __future__ import annotations
import re
import r2p33_candidate as p33
import pulse_search_r2p31 as p31

REWRITES = (
    (r'\b(?:historical|previous|past)\s+editions\s+of\s+', 'history of '),
    (r'\bwhat\s+were\s+the\b', 'the'),
    (r'\bbooking\b', 'book'),
    (r'\bwork\s*\??\s*$', ''),
    (r'\beditions\b', 'over the years'),
    (r'\bapart\s+from\b', 'excluding'),
)

# Extract a user-written named series from a history request, rather than use
# an event-specific exception. Keep its explicit name (including London) when
# titles also contain lookalike series from different organisers.
_SERIES_NAME = (
    re.compile(r'\b(?:about|during|of|the)\s+([\w\-\s\'’]{3,90}?)\s+(?:over\s+the\s+years|through\s+the\s+years|across\s+the\s+years|editions)\b', re.I),
    re.compile(r'\beditions\s+of\s+([\w\-\s\'’]{3,90})\s*[?.!]*$', re.I),
    re.compile(r'\bhistory\s+of\s+([\w\-\s\'’]{3,90})\s*[?.!]*$', re.I),
)


def reformulate(query: str) -> str:
    result = query
    for pattern, replacement in REWRITES:
        result = re.sub(pattern, replacement, result, flags=re.I)
    return re.sub(r'\s+', ' ', result).strip()


def _series_phrase(query):
    for pat in _SERIES_NAME:
        m = pat.search(query)
        if m:
            phrase = m.group(1).strip(" .'\"?!")
            toks = p31.words(phrase)
            while toks and toks[0] in {'past', 'historical', 'previous', 'recent'}:
                toks = toks[1:]
            if len(toks) >= 2:
                return toks
    return []


def _contiguous(sub, seq):
    return any(seq[i:i+len(sub)]==sub for i in range(len(seq)-len(sub)+1))


def rank(query, rows, limit=5):
    if not isinstance(query, str) or not query.strip():
        return p33.rank(query, rows, limit)
    reformed = reformulate(query)
    # Get a larger candidate set for series: downstream filtering must not be
    # limited by an irrelevant similarly-named first-page item.
    phrase = _series_phrase(reformed)
    matches, status, spec = p33.rank(reformed, rows, limit=max(limit, 40) if phrase else limit)
    spec = dict(spec)
    if phrase and spec.get('kind') == 'series' and matches:
        strict = [r for r in matches if _contiguous(phrase, p31.words(r['title']))]
        if strict:
            matches = strict
            spec['series_identity_filter'] = 'CONTIGUOUS_QUERY_NAME_IN_TITLE'
            spec['series_identity_terms'] = phrase
        else:
            # Unrecognised named series is not permission to silently return a
            # similar unrelated event. Do not widen the result set.
            matches = []
            spec['series_identity_filter'] = 'NO_EXACT_NAMED_SERIES'
    matches = matches[:limit]
    status = ('MATCHES_UNVERIFIED' if matches else ('WITHHELD_NO_SUPPORTED_INDEX_MATCH' if status=='MATCHES_UNVERIFIED' else status))
    spec['reformulated'] = reformed != query
    return matches, status, spec
