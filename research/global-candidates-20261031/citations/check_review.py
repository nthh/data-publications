#!/usr/bin/env python3
"""Nonmutating crosswalk, frozen-selection, candidate, and citation preservation checks."""
import collections,json,sys,yaml
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; C=Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'scripts'))
from record_locations import record_paths
frozen=json.loads((ROOT/'research/catalog-citations-20261030/groups-combined-active-global.json').read_text())[:50]
selected=json.loads((C/'selected-groups.json').read_text()); review=json.loads((C/'reviewed.json').read_text())
assert selected==frozen and len(selected)==50 and review['group_count']==50
assert len(review['candidates'])==53 and review['candidate_count']==53
expected=collections.Counter((rank,e['catalog'],e['catalog_id']) for rank,g in enumerate(frozen,1) for e in g['entries'])
observed=collections.Counter((c['source_group_rank'],'official' if s['provider']=='Google Earth Engine official catalog' else 'community',s['entry_id']) for c in review['candidates'] for s in c['sources'])
assert expected==observed, f'candidate source entry mismatch: {expected-observed} / {observed-expected}'
canon={}
for p in record_paths(ROOT):
 d=yaml.safe_load(p.read_text()) or {}; a=d.get('audit') or {}
 if a.get('family_key'): canon[a['family_key']]=d['id']
for rank,g in enumerate(frozen,1):
 cs=[c for c in review['candidates'] if c['source_group_rank']==rank]
 assert len(cs)>=1
 for c in cs:
  assert c['citation']['work_id']==g['id'] and c['citation']['doi']==g['top_paper_doi'].removeprefix('https://doi.org/')
  assert c['citation']['count']==g['max_paper_citations'] and c['citation']['count_date']=='2026-10-30'
  assert c['citation']['frozen_evidence_key']==g['id'] and c['source_group_candidate_count']==len(cs)
  community=[s for s in c['sources'] if s['provider']=='Earth Engine Community Catalog']
  matches={m['source_entry_id']:m['existing_record_id'] for m in c.get('community_record_matches',[])}
  for s in community:
   if s['entry_id'] in canon: assert matches.get(s['entry_id'])==canon[s['entry_id']], (rank,s['entry_id'],matches,canon.get(s['entry_id']))
assert len({c['suggested_id'] for c in review['candidates']})==len(review['candidates'])
ff=next(c for c in review['candidates'] if c['source_group_rank']==17)
assert ff['existing_record_id']=='free-flowing-rivers' and '10.1038/s41586-019-1111-9' in ff['canonical_match_basis']
for rank in (14,27,28): assert len([c for c in review['candidates'] if c['source_group_rank']==rank])==2
print('OK: frozen 50 groups retained; 53 unique candidates; per-source family matches and frozen citations preserved')
