#!/usr/bin/env python3
"""Prepare a small, exact README-only upload plan from validated current records."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_products
sys.path.insert(0, str(ROOT / 'scripts/source_publish'))
import upload


def main():
    output = Path(sys.argv[1])
    if output.exists():
        raise ValueError('Choose a new plan filename')
    products, readmes = [], []
    for dataset, record in source_products.load_records(ROOT).items():
        if (record.get('publication') or {}).get('status') != 'published':
            continue
        draft, _, readme = source_products.draft_for(ROOT, record)
        path = f'datasets/{dataset}/source-coop/product-README.md'
        body = readme.encode()
        if (ROOT / path).read_bytes() != body or 'folia' in readme.casefold():
            raise ValueError(f'Unexpected README contents: {dataset}')
        key = f'{draft["product_id"]}/README.md'
        products.append({'dataset_id': dataset, 'product_id': draft['product_id'],
                         'owner': draft['owner'], 'bucket': draft['owner'],
                         'endpoint': 'https://data.source.coop', 'release': draft['release']})
        readmes.append({'bucket': draft['owner'], 'endpoint': 'https://data.source.coop',
                        'object_key': key, 'size_bytes': len(body),
                        'sha256': hashlib.sha256(body).hexdigest(), 'content_type': 'text/markdown',
                        's3_uri_proposed': f's3://{draft["owner"]}/{key}',
                        'raw_url_proposed': f'https://data.source.coop/{draft["owner"]}/{key}',
                        'source': {'kind': 'repository', 'path': path}, 'mutable': True,
                        'binding_status': 'canonical_generated_consumer_copy'})
    if len(products) != 5:
        raise ValueError('Expected the five reviewed published products')
    plan = {'schema_version': 1, 'plan_type': 'source_coop_immutable_exact_file_plan',
            'execution': 'not_started', 'scope': 'Five mutable product-root READMEs only.',
            'products': products, 'files': [], 'file_count': 0, 'total_bytes': 0,
            'mutable_metadata': readmes, 'mutable_metadata_count': len(readmes)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True)+'\n')
    for product in products:
        _, selected = upload.load_plan(output, product['dataset_id'], False, readme_only=True)
        resolved = upload.resolve_sources(selected, {}, {}, ROOT)
        if len(resolved) != 1:
            raise ValueError('Expected exactly one README per product')
        entry, path = resolved[0]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Local README differs from plan')
    print(json.dumps({'status': 'prepared', 'readmes': len(readmes),
                      'bytes': sum(row['size_bytes'] for row in readmes),
                      'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
