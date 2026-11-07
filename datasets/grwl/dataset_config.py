"""Pinned GRWL source/build settings."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import yaml
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
def load_config():
    record = yaml.safe_load((HERE / 'dataset.yaml').read_text())
    return {'id': record['id'], 'title': record['title'], **record['source']}
def config_sha256(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
