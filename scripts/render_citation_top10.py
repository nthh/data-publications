#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["Pillow==13.0.0"]
# ///
"""Render the frozen overall citation top ten with geography.

Run: uv run --script scripts/render_citation_top10.py
Default fonts are macOS Arial; use --font-regular and --font-bold elsewhere.
The PNG embeds the source hash and displayed data for inspection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "merrav2": "MERRA-2 daily/derived fields*",
    "plastic": "River plastic inputs",
    "terraclim": "TerraClimate warming scenarios*",
    "prism_daily": "PRISM daily",
    "prism_monthly": "PRISM monthly",
    "isric": "SoilGrids 2.0",
    "glacier": "Global glacier elevation change",
    "hydrolakes": "HydroLAKES",
    "mapbiomas": "MapBiomas",
    "gfch": "Forest canopy height — GEDI/Landsat",
}
REGIONS = {
    "prism_daily": "Conterminous U.S.",
    "prism_monthly": "Conterminous U.S.",
    "mapbiomas": "South America\n& Indonesia",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/community-catalog-top-10-overall.png")
    parser.add_argument("--font-regular", type=Path, default=Path("/System/Library/Fonts/Supplemental/Arial.ttf"))
    parser.add_argument("--font-bold", type=Path, default=Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
    args = parser.parse_args()
    source = ROOT / "research/citations/rankings.json"
    raw = source.read_bytes()
    records = json.loads(raw)
    snapshot = json.loads((ROOT / "research/citations/methodology.json").read_text())
    assert snapshot["as_of"] == "2026-10-29"
    matched = [r for r in records if r.get("max_paper_citations") is not None]
    ranked = sorted(matched, key=lambda r: (-r["max_paper_citations"], r["slug"]))[:10]
    assert len(ranked) == 10 and {r["slug"] for r in ranked} == set(LABELS)
    displayed = []
    for r in ranked:
        region = REGIONS.get(r["slug"])
        if region is None:
            assert r["geographic_scope"] == "global"
            region = "Global"
        displayed.append({"dataset": LABELS[r["slug"]], "region": region.replace("\n", " "),
                          "citations": r["max_paper_citations"], "community_url": r["community_url"],
                          "paper_doi": r["top_paper_doi"]})

    scale = 2
    width, height = 1480, 1190
    canvas = Image.new("RGB", (width * scale, height * scale), "#ffffff")
    draw = ImageDraw.Draw(canvas)
    def font(size, bold=False):
        return ImageFont.truetype(str(args.font_bold if bold else args.font_regular), int(size * scale))
    def text(x, y, value, f, color="#142d3c", anchor="lt"):
        draw.text((x * scale, y * scale), value, font=f, fill=color, anchor=anchor)
    def box(coords, fill):
        draw.rectangle(tuple(int(n * scale) for n in coords), fill=fill)
    def line(coords, fill="#e4eaee"):
        draw.line(tuple(int(n * scale) for n in coords), fill=fill, width=scale)

    text(64, 42, "GEE COMMUNITY CATALOG", font(17, True), "#177a82")
    text(64, 85, "Most-cited community datasets", font(48, True))
    text(64, 151, "Top 10 overall  •  All geographic scopes  •  29 October 2026", font(22), "#526975")
    text(64, 189, f"Associated-paper citation counts available for {len(matched)} of {len(records)} catalog entries.", font(18), "#637681")

    left, right, table_y, header_h, row_h = 64, 1416, 236, 56, 72
    rank_x, name_x, region_x, count_x = 88, 168, 886, 1388
    box((left, table_y, right, table_y + header_h), "#163b4b")
    text(rank_x, table_y + 28, "#", font(19, True), "#ffffff", "lm")
    text(name_x, table_y + 28, "Dataset", font(20, True), "#ffffff", "lm")
    text(region_x, table_y + 28, "Region", font(20, True), "#ffffff", "lm")
    text(count_x, table_y + 28, "Citations", font(20, True), "#ffffff", "rm")

    for i, record in enumerate(ranked):
        y = table_y + header_h + i * row_h
        if i % 2 == 0:
            box((left, y, right, y + row_h), "#f4f7f9")
        name = LABELS[record["slug"]]
        assert draw.textlength(name, font=font(26)) < (region_x - name_x - 34) * scale
        text(rank_x, y + row_h / 2, str(i + 1), font(23), "#637681", "lm")
        text(name_x, y + row_h / 2, name, font(26), anchor="lm")
        region_lines = REGIONS.get(record["slug"], "Global").split("\n")
        for j, value in enumerate(region_lines):
            text(region_x, y + row_h / 2 + (j - (len(region_lines) - 1) / 2) * 27,
                 value, font(22), "#435d6b", "lm")
        text(count_x, y + row_h / 2, f"{record['max_paper_citations']:,}", font(28, True), "#126970", "rm")
        line((left, y + row_h, right, y + row_h))

    text(64, 1042, "Source: OpenAlex snapshot (29 Oct 2026) and the GEE Community Catalog citation audit.", font(17, True), "#435d6b")
    text(64, 1072, "Metric: highest citation count among associated papers per entry; unmatched entries are excluded.", font(16), "#637681")
    text(64, 1096, "* MERRA-2 and TerraClimate counts refer to base-product papers, not these exact derived releases.", font(16), "#637681")
    text(64, 1120, "PRISM daily and monthly share one paper. Counts are not summed across entries. Geography follows the saved family review.", font(16), "#637681")
    text(64, 1154, "gee-community-catalog.org", font(15), "#177a82")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Title", "GEE Community Catalog — Top 10 overall by associated-paper citations")
    metadata.add_text("Snapshot", snapshot["as_of"])
    metadata.add_text("SourceSHA256", hashlib.sha256(raw).hexdigest())
    metadata.add_text("TableData", json.dumps(displayed, ensure_ascii=False))
    metadata.add_text("FontSHA256", json.dumps({"regular": hashlib.sha256(args.font_regular.read_bytes()).hexdigest(), "bold": hashlib.sha256(args.font_bold.read_bytes()).hexdigest()}))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, pnginfo=metadata, optimize=True, dpi=(192, 192))
    with Image.open(args.output) as check:
        check.verify()
    print(json.dumps({"output": str(args.output), "pixels": [width * scale, height * scale], "rows": len(displayed),
                      "source_sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": args.output.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
