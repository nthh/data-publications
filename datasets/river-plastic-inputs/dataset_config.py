"""Read the single canonical dataset record and its effective build settings."""
from pathlib import Path
import hashlib
import json
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_config():
    record = yaml.safe_load((HERE / "dataset.yaml").read_text())
    if set(record["source"]) & set(record["build"]):
        raise ValueError("Source and build settings overlap")
    config = {"id": record["id"], "title": record["title"], **record["source"], **record["build"]}
    if config["id"] != HERE.name:
        raise ValueError("Dataset ID differs from its directory")
    return config


def config_sha256(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
