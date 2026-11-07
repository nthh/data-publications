#!/usr/bin/env python3
"""Build/check the supplementary literature candidate projection; never overwrites by default."""
import argparse,datetime as dt,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[2]
ids=json.loads((HERE/'paper-identities.json').read_text()); responses=json.loads((HERE/'openalex-responses-20261101.json').read_text())
response_map={(x['candidate_id'],x['doi_role']):x for x in responses['records']}
exact_editions={'earthstat_monfreda_crop_maps_2000','glim_global_lithological_map_v1','era_interim','hyde_32','gmia_v5'}
formats={
'worldclim_v2':['GeoTIFF'],'cru_ts_v4':['NetCDF','space-separated ASCII'],'chelsa_climatologies':['GeoTIFF'],'gpcc_full_data_monthly_v2022':['gzip-compressed NetCDF'],'earthstat_monfreda_crop_maps_2000':['GeoTIFF'],'glim_global_lithological_map_v1':[],'era_interim':['GRIB','NetCDF (ECMWF converted output)'],'modis_mcd12q1_land_cover_c061':['HDF-EOS'],'hyde_32':[],'gmia_v5':['zipped ASCII grid','Esri Shapefile']}
access={
'worldclim_v2':('download_available','Producer page provides downloadable resolution-specific archives. Exact release remains separate from WorldClim v1.'),
'cru_ts_v4':('download_available','CRU producer/CRU website and CEDA archive offer gridded releases; station support varies by cell.'),
'chelsa_climatologies':('download_available','Producer lists direct downloads; v2.1 is a later release than the 2017 paper’s v1 dataset.'),
'gpcc_full_data_monthly_v2022':('download_available','DWD GPCC download gate offers versioned precipitation products; the full-data monthly product is an offline analysis release.'),
'earthstat_monfreda_crop_maps_2000':('download_available','EarthStat provides direct global crop-area/yield raster downloads.'),
'glim_global_lithological_map_v1':('download_available','PANGAEA dataset record provides the gridded release; companion map and rasterized grid are distinct representations.'),
'era_interim':('download_available','ECMWF lists the archived 1979–August 2019 reanalysis and advises migration to ERA5; access conditions may apply.'),
'modis_mcd12q1_land_cover_c061':('download_available','NASA DAAC product documentation describes the global annual MCD12Q1 family; current candidate edition differs from the Collection 5 paper.'),
'hyde_32':('download_available','Producer portal provides global-scale HYDE layers and links to the versioned dataset deposit.'),
'gmia_v5':('download_available','FAO AQUASTAT links to the producer GMIA v5 report/data; do not confuse area equipped with actual irrigated area.')}
entries=[]
for p in ids['papers']:
    ident=p['paper']; doi=ident['doi']; raw=response_map.get((p['suggested_id'],'primary'),{})
    work=raw.get('response') or {}
    doi_returned=(work.get('doi') or '').lower().rstrip('/')
    expected='https://doi.org/'+doi.lower()
    valid=bool(work.get('id') and doi_returned==expected and isinstance(work.get('cited_by_count'),int))
    count=work.get('cited_by_count') if valid else None
    obs=raw.get('requested_at')
    obsdate=obs[:10] if obs else None
    source_url=next((u for u in p['primary_urls'] if '/doi.org/' not in u and not u.startswith('https://doi.org/')),p['primary_urls'][0])
    producer=p['dataset_family'].split(' ')[0]
    existing=(p.get('existing_record_review') or {}).get('record_id')
    rel=(p.get('existing_record_review') or {}).get('relationship','new_family')
    rel_papers=[]
    for i,rp in enumerate(p.get('related_papers',[])+p.get('related_edition_papers',[]),1):
        rr=response_map.get((p['suggested_id'],f'related_{i}'),{}); rw=rr.get('response') or {}
        returned=(rw.get('doi') or '').lower().rstrip('/')
        rel_papers.append({'doi':rp['doi'],'title':rp.get('title'),'work_id':rw.get('id'),'count':rw.get('cited_by_count') if returned==('https://doi.org/'+rp['doi'].lower()) and isinstance(rw.get('cited_by_count'),int) else None,'observed_at':rr.get('requested_at'),'provider':'OpenAlex','identity_note':rp.get('note'),'used_for_candidate_count':False,'lookup_status':'matched' if returned==('https://doi.org/'+rp['doi'].lower()) and rw.get('id') else ('api_error_or_unresolved' if not rw.get('id') else 'doi_mismatch')})
    status,summary=access[p['suggested_id']]
    source_records=[{'provider':producer,'entry_id':p['dataset_family'],'url':source_url,'relationship':'same_family' if not existing else 'related_release','edition':p.get('product_edition')}]
    source_records.append({'provider':'Primary paper/publisher','entry_id':doi,'url':'https://doi.org/'+doi,'relationship':'associated_dataset_publication'})
    evidence=list(dict.fromkeys(p['primary_urls']+[('https://doi.org/'+p.get('data_doi')) if p.get('data_doi') else None])); evidence=[x for x in evidence if x]
    c={'suggested_id':p['suggested_id'],'existing_record_id':None,'related_record_id':existing,'title':p['dataset_family'],'geographic_scope':p['geographic_scope'],'spatial_coverage':p['spatial_coverage'],'sources':source_records,'observed_formats':formats[p['suggested_id']],'format_labels':{'worldclim_v2':['raster'],'cru_ts_v4':['raster','time-series'],'chelsa_climatologies':['raster'],'gpcc_full_data_monthly_v2022':['raster','time-series'],'earthstat_monfreda_crop_maps_2000':['raster'],'glim_global_lithological_map_v1':['raster','vector'],'era_interim':['raster','time-series'],'modis_mcd12q1_land_cover_c061':['raster','time-series'],'hyde_32':['raster','time-series'],'gmia_v5':['raster','vector']}[p['suggested_id']],'recommended_formats':{'worldclim_v2':['COG'],'cru_ts_v4':['Zarr'],'chelsa_climatologies':['COG'],'gpcc_full_data_monthly_v2022':['Zarr'],'earthstat_monfreda_crop_maps_2000':['COG'],'glim_global_lithological_map_v1':['COG','GeoParquet'],'era_interim':['Zarr'],'modis_mcd12q1_land_cover_c061':['COG'],'hyde_32':['Zarr'],'gmia_v5':['COG']}[p['suggested_id']],'format_observation_note':'Producer documentation identifies formats listed in observed_formats.' if formats[p['suggested_id']] else 'Reviewed producer/publisher metadata established spatial structure but did not identify a downloadable file format; observed_formats is intentionally empty.' ,'format_recommendation_note':'Recommended format is a proposed future access derivative based on the product’s grid/temporal or vector structure; it was not observed in a producer download and is not a format-validation claim.','hosting_status':status,'access_summary':summary,'conversion_rationale':'Supplementary literature discovery only. A high associated-paper count is evidence of a documented product family, not exact-edition usage, conversion priority, or native-format readiness. Review producer bytes, terms and existing record component coverage before promotion.','license_summary':'Exact release terms need product-specific review; no redistribution permission is inferred from literature or access pages.','evidence_urls':evidence,'proposed_outputs':['Confirm exact product edition, component scope, native data format, access and license; compare against any existing canonical record before proposing conversion.'],'citation':{'doi':doi,'work_id':work.get('id') if valid else None,'work_title':work.get('title') if valid else ident.get('title'),'count':count,'count_date':obsdate,'count_observed_at':obs,'count_provider':'OpenAlex public API','count_scope':ident['citation_scope'],'lookup_status':'matched' if valid else ('api_error_or_unresolved' if not work.get('id') else 'doi_mismatch'),'api_http_status':raw.get('status'),'evidence_path':'research/global-candidates-20261031/literature/openalex-responses-20261101.json','evidence_key':p['suggested_id'],'count_is_exact_edition':p['suggested_id'] in exact_editions},'product_edition':p['product_edition'],'data_doi':p.get('data_doi'),'identity_review_path':'research/global-candidates-20261031/literature/paper-identities.json','related_record_relationship':rel,'identity_notes':ident.get('edition_note'),'related_paper_counts':rel_papers}
    entries.append(c)
# Fail closed if any primary identity DOI falls within the prior frozen top-50 candidate groups.
selected=json.loads((ROOT/'research/catalog-citations-20261030/groups-combined-active-global.json').read_text())[:50]
frozen_dois={g['top_paper_doi'].lower().replace('https://doi.org/','').rstrip('/') for g in selected}
for c in entries:
    if c['citation']['doi'].lower() in frozen_dois: raise SystemExit(f"DOI overlaps frozen top-50: {c['citation']['doi']}")
result={'schema_version':1,'provider':'OpenAlex public API DOI-resolved work counts','observed_at':responses['captured_at'],'lane':'supplementary_global_literature_sample','selection_note':'Ten documented global producer dataset families absent from the frozen top-50 shared-paper group set. Bounded purposive sample; not a universal top-cited geospatial-dataset ranking.','paper_identity_path':'research/global-candidates-20261031/literature/paper-identities.json','count_evidence_path':'research/global-candidates-20261031/literature/openalex-responses-20261101.json','request_count':responses['query_count'],'candidate_count':len(entries),'candidates':entries,'limitations':['This supplementary sample was purposively selected from known producer dataset papers; it is not a literature-wide search or exhaustive citation leaderboard.','OpenAlex cited_by_count is observed on each request timestamp. It is separate from the frozen 2026-10-30 catalog study and must not be mixed into its ranking.','Paper citations may describe a product family or older release. Per-edition limitations appear in identity notes; citation count does not establish exact-release use.','Primary DOI lookup failures or DOI/title mismatches remain null/unresolved. Data release DOI citations are not queried or combined with paper counts.','No data assets were requested or downloaded; access and license notes are metadata observations, not validation of contents or legal rights.']}
text=json.dumps(result,indent=2,ensure_ascii=False)+'\n'
out=HERE/'reviewed.json'
ap=argparse.ArgumentParser(); mode=ap.add_mutually_exclusive_group(); mode.add_argument('--write',action='store_true',help='create reviewed.json only if it does not exist'); mode.add_argument('--refresh',action='store_true',help='explicitly regenerate the derived reviewed.json'); mode.add_argument('--check',action='store_true',help='compare without writing (default)'); args=ap.parse_args()
if args.write or args.refresh:
    if out.exists() and not args.refresh: ap.error(f'refusing to overwrite {out}; use --refresh only for explicit regeneration')
    out.write_text(text); print(f'Wrote {out}' + (' (explicit refresh)' if args.refresh else ' (new file only)'))
else:
    if not out.exists() or out.read_text()!=text: print('FAIL: reviewed.json differs; --check did not write files',file=sys.stderr); sys.exit(1)
    print('OK: reviewed.json exactly matches identity and captured OpenAlex evidence; no files written')
