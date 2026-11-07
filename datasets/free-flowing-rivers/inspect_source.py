#!/usr/bin/env python3
"""Inspect a pinned File Geodatabase ZIP without extracting its contents."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import pyogrio

EXPECTED_SIZE = 954710486
EXPECTED_MD5 = "2df6c603904f61f5dc482d3f9873900f"
DESCRIPTIONS = {
    "OBJECTID": "Esri-generated feature identifier; unique row identifier within this release.",
    "REACH_ID": "River reach identifier used to link to HydroATLAS.",
    "GOID": "Global object identifier used to identify a reach across free-flowing-river assessments and link dams to reaches.",
    "NOID": "Network object identifier; same purpose as GOID.",
    "NUOID": "One or more upstream NOIDs separated by underscores; an empty value identifies a headwater reach.",
    "NDOID": "Next downstream NOID; zero denotes a terminal reach.",
    "CON_ID": "Continent identifier: 1 North America, 2 South America, 3 Europe, 4 Africa, 5 Asia, 6 Australia.",
    "CONTINENT": "Continent name; boundaries are delineated from HydroBASINS.",
    "COUNTRY": "Country name.",
    "BAS_ID": "HydroSHEDS hydrological river basin identifier.",
    "BAS_NAME": "Hydrological basin name when available.",
    "LENGTH_KM": "Length of the river reach.",
    "VOLUME_TCM": "Volume of the reach channel, calculated from width, length, and depth.",
    "UPLAND_SKM": "Upstream watershed area of the river reach.",
    "DIS_AV_CMS": "Average long-term (1971–2000) naturalized discharge.",
    "RIV_ORD": "River order calculated from long-term average discharge using logarithmic classes.",
    "ERO_YLD_TON": "Erosion yield summed within the river reach catchment; not accumulated along the network.",
    "HYFALL": "Presence (1) or absence (0) of one or more waterfalls along the reach.",
    "BB_ID": "Backbone river identifier for a contiguous source-to-terminus flow path.",
    "BB_NAME": "Backbone river name.",
    "BB_LEN_KM": "Backbone river length, the sum of its reach lengths.",
    "BB_DIS_ORD": "Discharge order of the most downstream reach in the backbone river.",
    "BB_VOL_TCM": "Backbone river volume, the sum of its reach volumes.",
    "BB_OCEAN": "Indicates whether the backbone river is directly connected to the ocean (1) or not (0).",
    "INC": "Analysis filter: Grill et al. (2019) included reaches with value 1 in analysis results.",
    "DOF": "Degree of fragmentation pressure index (0–100%).",
    "DOR": "Degree of regulation pressure index (0–100%).",
    "SED": "Sediment trapping pressure index (0–100%).",
    "USE": "Water consumption pressure index (0–100%).",
    "URB": "Urbanization pressure index (0–100%).",
    "RDD": "Road construction pressure index (0–100%).",
    "FLD": "Inundation (floodplain) extent in the river reach catchment (%).",
    "CSI": "Connectivity Status Index (0–100%); 100% is full connectivity.",
    "CSI_D": "Dominant pressure factor; documented values include DOF, DOR, SED, USE, RDD, and URB.",
    "CSI_FF": "Indicates whether CSI is below (0) or above (1) the 95% free-flowing threshold.",
    "CSI_FF1": "Two-category free-flowing status: free-flowing (1) or non-free-flowing (3).",
    "CSI_FF2": "Three-category status: free-flowing (1), good connectivity (2), or impacted (3).",
    "CSI_FFID": "Identifier for contiguous river stretches.",
    "Shape_Length": "Length value maintained by the ESRI File Geodatabase; see LENGTH_KM for reach length.",
    "Shape": "Source MultiLineString reach geometry, stored as WKB without coordinate transformation.",
}
UNITS = {
    "LENGTH_KM": "km",
    "VOLUME_TCM": "thousand cubic metres",
    "UPLAND_SKM": "km²",
    "DIS_AV_CMS": "m³/s",
    "ERO_YLD_TON": "tonnes/year",
    "BB_LEN_KM": "km",
    "BB_VOL_TCM": "thousand cubic metres",
    "DOF": "%",
    "DOR": "%",
    "SED": "%",
    "USE": "%",
    "URB": "%",
    "RDD": "%",
    "FLD": "%",
    "CSI": "%",
}


def hash_file(path: Path) -> dict[str, str | int]:
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            size += len(block)
            sha.update(block)
            md5.update(block)
    return {"size_bytes": size, "md5": md5.hexdigest(), "sha256": sha.hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    pin = hash_file(source)
    if pin["size_bytes"] != EXPECTED_SIZE or pin["md5"] != EXPECTED_MD5:
        raise SystemExit(f"Figshare source pin mismatch: {pin}")

    with zipfile.ZipFile(source) as archive:
        bad = archive.testzip()
        if bad:
            raise SystemExit(f"ZIP CRC failure in {bad}")
        gdb_roots = sorted(
            {name.split(".gdb/", 1)[0] + ".gdb" for name in archive.namelist() if ".gdb/" in name}
        )
    if len(gdb_roots) != 1:
        raise SystemExit(f"Expected exactly one File Geodatabase in ZIP, found {gdb_roots}")
    vfs_path = f"/vsizip/{source}/{gdb_roots[0]}"
    layers = []
    for layer_name, geometry_type in pyogrio.list_layers(vfs_path):
        info = pyogrio.read_info(vfs_path, layer=layer_name)
        layers.append(
            {
                "name": layer_name,
                "geometry_type_from_list": geometry_type,
                "feature_count": info["features"],
                "geometry_type": info["geometry_type"],
                "crs": info["crs"],
                "fields": [
                    {"name": name, "dtype": str(dtype)}
                    for name, dtype in zip(info["fields"], info["dtypes"], strict=True)
                ],
                "fid_column": info["fid_column"],
                "geometry_name": info["geometry_name"],
                "total_bounds": info["total_bounds"],
                "driver": info["driver"],
            }
        )
    with pyogrio.open_arrow(vfs_path, layer=layers[0]["name"], return_fids=True, batch_size=1, use_pyarrow=True) as (_, reader):
        arrow_schema = next(reader).schema
    field_dictionary = []
    schema_fields = list(arrow_schema)
    for item in schema_fields:
        if item.name == "Shape":
            source_type = "MultiLineString"
        else:
            source_type = str(item.type)
        field_dictionary.append(
            {
                "name": item.name,
                "type": source_type,
                "nullable": item.nullable,
                "description": DESCRIPTIONS[item.name],
                "unit": UNITS.get(item.name),
                "source_field_metadata": {k.decode(): v.decode() for k, v in (item.metadata or {}).items()},
            }
        )
    report = {
        "source_url": "https://ndownloader.figshare.com/files/15090536",
        "source_name": source.name,
        "article_doi": "10.6084/m9.figshare.7688801.v1",
        "article_version": 1,
        "license": "CC-BY-4.0",
        "archive": pin,
        "zip_crc": "passed",
        "gdb_path_in_zip": gdb_roots[0],
        "field_dictionary": field_dictionary,
        "layers": layers,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
