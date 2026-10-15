"""English figures and presentation tables from frozen model outputs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from .artifacts import resolve_artifact


def generate_publication(root: Path, folder: Path | None = None, *, book=True,
                         rerender_legacy=True, publication=True):
    from .publication_maps import build_maps
    from .publication_charts import build_charts
    from .publication_tables import build_tables, rerender_cached_reports
    root=Path(root).resolve()
    folder=Path(folder or root/"outputs/publication").resolve()
    required=["outputs/extensions/dpi_drivers/predictions.csv",
              "outputs/history/gli_hog_aligned_panel.csv",
              "outputs/main/scenario_summary.csv"]
    missing=[p for p in required if not resolve_artifact(root/p).is_file()]
    if missing:
        raise FileNotFoundError("Missing frozen outputs: "+", ".join(missing)+
            ". Prepare the original analysis with python run.py --offline --simulate "
            "and the extension with python run_extensions.py --offline --run.")
    folder.mkdir(parents=True,exist_ok=True)
    if rerender_legacy: rerender_cached_reports(root)
    figures=build_maps(root,folder,publication=publication)
    figures+=build_charts(root,folder,publication=publication)
    figures.sort(key=lambda item:(item["role"]!="main",item["id"]))
    tables=build_tables(root,folder/"tables")
    for item in tables:
        for key in ("csv","markdown"):
            item[key]=str(Path(item[key]).relative_to(folder))
    for item in figures:
        item["files"]={extension:f"{item['stem']}_{suffix}.{extension}"
            for extension,suffix in (("svg","master"),("pdf","master"))}
        item["files"].update(png_300=f"{item['stem']}_300dpi.png",data=f"{item['stem']}_data.csv")
        if publication: item["files"]["png_600"]=f"{item['stem']}_600dpi.png"
    payload={"language":"English","generated_utc":datetime.now(timezone.utc).isoformat(),
             "last_DPI_observation":"2023-01-01","last_GLI_source_observation":"2020-12-31",
             "figures":figures,"tables":tables,
             "scope":"Presentation exports only; no model fitting or political recoding."}
    (folder/"publication_manifest.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    lines=["# English figure and table outputs","",
           "Observed data end in January 2023 (DPI) and December 2020 (GLI).",
           "All captions distinguish observed evidence from conditional simulations.","",
           "## Figures",""]
    for item in figures:
        lines += [f"### {item['id'].replace('_',' ')}. {item['title']}","",
                  f"![{item['title']}]({item['stem']}_300dpi.png)","",item["caption"],"",
                  "Source: "+item["source"],"",
                  f"[Vector SVG]({item['stem']}_master.svg) · [Vector PDF]({item['stem']}_master.pdf)",""]
    lines += ["## Tables",""]
    for item in tables:
        lines += [f"- [{item['id'].replace('_',' ')}: {item['title']}](tables/{item['stem']}.md)"]
    (folder/"README.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    if book:
        from .publication_book import build_book
        build_book(folder,figures,tables)
    inventory={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(folder.rglob("*")) if p.is_file() and p.name!="file_hashes.json"}
    (folder/"file_hashes.json").write_text(json.dumps(inventory,indent=2)+"\n",encoding="utf-8")
    return payload


def main(root: Path):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder",type=Path,help="Output folder (default outputs/publication)")
    parser.add_argument("--no-book",action="store_true",help="Skip the captioned PDF book")
    parser.add_argument("--no-legacy",action="store_true",help="Skip English re-rendering of legacy diagnostics")
    parser.add_argument("--review-only",action="store_true",help="Write 300 dpi PNGs, omit 600 dpi exports")
    args=parser.parse_args()
    result=generate_publication(root,args.folder,book=not args.no_book,
                               rerender_legacy=not args.no_legacy,publication=not args.review_only)
    print(f"English outputs: {len(result['figures'])} figures and {len(result['tables'])} tables")

