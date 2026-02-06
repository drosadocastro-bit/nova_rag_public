#!/usr/bin/env python3
"""
Build a diagram manifest for ALL manuals.

This script scans PDFs under a root directory (default: data/), extracts embedded
images (diagrams/schematics), stores them under data/diagrams/, and writes a
JSONL manifest mapping each diagram to its source PDF and page.

Deterministic, offline-only. No network calls.

Usage:
    python scripts/build_diagram_manifest.py
    python scripts/build_diagram_manifest.py --pdf-root data --output-root data/diagrams
    python scripts/build_diagram_manifest.py --max-pages 50 --min-bytes 20000
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


COMPONENT_KEYWORDS = {
    "antenna": ["antenna", "feed", "feedhorn", "feed horn", "radome"],
    "duplexer": ["duplexer", "tr", "t/r", "tr switch", "circulator"],
    "transmitter": ["transmitter", "tx", "magnetron", "klystron", "modulator"],
    "receiver": ["receiver", "rx", "lna", "preamplifier", "mixer", "if"],
    "processor": ["processor", "signal processor", "dsp", "data processor"],
    "display": ["display", "indicator", "ppi", "console"],
    "power": ["power", "psu", "power supply", "hv", "high voltage"],
    "timing": ["timing", "sync", "synchronizer", "trigger"],
    "waveguide": ["waveguide", "transmission line", "coax", "rf path"],
    "test_point": ["test point", "tp", "test jack", "monitor"],
}


def extract_components(text: str, filename: str) -> list[str]:
    """Extract component tags from page text and filename (deterministic)."""
    tags = set()
    hay = f"{text or ''} {filename or ''}".lower()
    for comp, keywords in COMPONENT_KEYWORDS.items():
        for kw in keywords:
            if kw in hay:
                tags.add(comp)
                break
    return sorted(tags)


def iter_pdfs(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.pdf"):
        if path.is_file():
            yield path


def safe_stem(path: Path) -> str:
    stem = path.stem.replace(" ", "_")
    return "".join(c for c in stem if c.isalnum() or c in {"_", "-"})


def extract_images_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    max_pages: int = 0,
    min_bytes: int = 10240,
    partial_mode: bool = False,
) -> list[dict]:
    """Extract images from a PDF and return manifest entries."""
    entries = []
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as e:
        if partial_mode and "jbig2dec" in str(e).lower():
            print(f"{pdf_path.name}: skipped (jbig2dec unavailable - partial mode)")
            return []
        raise RuntimeError(f"Failed to open PDF: {e}")
    total_pages = len(reader.pages)
    page_limit = total_pages if max_pages <= 0 else min(max_pages, total_pages)

    skipped_jbig2 = 0

    for page_index in range(page_limit):
        try:
            page = reader.pages[page_index]
            page_text = ""
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            try:
                images = getattr(page, "images", []) or []
            except Exception as e:
                if partial_mode and "jbig2dec" in str(e).lower():
                    skipped_jbig2 += 1
                    continue
                raise
            if not images:
                continue

            for img_idx, image in enumerate(images, 1):
                try:
                    data = getattr(image, "data", None)
                except Exception as e:
                    # Fallback: Skip JBIG2 images when jbig2dec is unavailable
                    if partial_mode and "jbig2dec" in str(e).lower():
                        skipped_jbig2 += 1
                        continue
                    raise
                if not data:
                    continue
                if len(data) < min_bytes:
                    continue

                ext = getattr(image, "extension", None) or "bin"
                width = getattr(image, "width", None)
                height = getattr(image, "height", None)

                img_name = f"page_{page_index + 1:04d}_img_{img_idx:02d}.{ext}"
                img_path = output_dir / img_name
                img_path.write_bytes(data)

                components = extract_components(page_text, pdf_path.name)
                entries.append(
                    {
                        "diagram_id": f"{pdf_path.stem}_p{page_index + 1}_i{img_idx}",
                        "source_pdf": pdf_path.name,
                        "source_path": str(pdf_path.as_posix()),
                        "page": page_index + 1,
                        "image_index": img_idx,
                        "image_path": str(img_path.as_posix()),
                        "image_bytes": len(data),
                        "image_width": width,
                        "image_height": height,
                        "image_ext": ext,
                        "components": components,
                    }
                )
        except Exception as e:
            if partial_mode and "jbig2dec" in str(e).lower():
                skipped_jbig2 += 1
                continue
            raise

    if skipped_jbig2 > 0:
        print(f"{pdf_path.name}: skipped {skipped_jbig2} JBIG2 images (jbig2dec unavailable)")

    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Build diagram manifest for all manuals")
    parser.add_argument("--pdf-root", default="data", help="Root directory containing PDFs")
    parser.add_argument("--output-root", default="data/diagrams", help="Output directory for extracted images")
    parser.add_argument("--manifest", default="data/diagrams/diagrams_manifest.jsonl", help="Manifest output path")
    parser.add_argument("--max-pages", type=int, default=0, help="Max pages per PDF (0 = all)")
    parser.add_argument("--min-bytes", type=int, default=10240, help="Minimum image size in bytes")
    parser.add_argument("--only-pdf", action="append", default=[], help="Process only matching PDF filename(s)")
    parser.add_argument("--retry-once", action="store_true", help="Retry failed PDFs once")
    parser.add_argument("--partial", action="store_true", help="Partial mode: skip JBIG2 pages when decoder unavailable")
    args = parser.parse_args()

    pdf_root = Path(args.pdf_root)
    output_root = Path(args.output_root)
    manifest_path = Path(args.manifest)

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    all_entries = []
    pdfs = list(iter_pdfs(pdf_root))
    if not pdfs:
        print(f"No PDFs found under: {pdf_root}")
        return 1

    if args.only_pdf:
        only_set = {name.lower() for name in args.only_pdf}
        pdfs = [p for p in pdfs if p.name.lower() in only_set]
        if not pdfs:
            print(f"No PDFs matched --only-pdf: {sorted(only_set)}")
            return 1

    failed_pdfs: list[Path] = []
    for pdf_path in pdfs:
        manual_id = safe_stem(pdf_path)
        manual_dir = output_root / manual_id / "images"
        manual_dir.mkdir(parents=True, exist_ok=True)

        try:
            entries = extract_images_from_pdf(
                pdf_path,
                manual_dir,
                max_pages=args.max_pages,
                min_bytes=args.min_bytes,
                partial_mode=args.partial,
            )
            all_entries.extend(entries)
            print(f"{pdf_path.name}: extracted {len(entries)} images")
        except Exception as e:
            print(f"{pdf_path.name}: extraction failed ({e})")
            failed_pdfs.append(pdf_path)

    if failed_pdfs and args.retry_once:
        print(f"Retrying {len(failed_pdfs)} failed PDFs once...")
        for pdf_path in list(failed_pdfs):
            manual_id = safe_stem(pdf_path)
            manual_dir = output_root / manual_id / "images"
            manual_dir.mkdir(parents=True, exist_ok=True)
            try:
                entries = extract_images_from_pdf(
                    pdf_path,
                    manual_dir,
                    max_pages=args.max_pages,
                    min_bytes=args.min_bytes,
                    partial_mode=args.partial,
                )
                all_entries.extend(entries)
                print(f"{pdf_path.name}: extracted {len(entries)} images (retry)")
                failed_pdfs.remove(pdf_path)
            except Exception as e:
                print(f"{pdf_path.name}: retry failed ({e})")

    with open(manifest_path, "w", encoding="utf-8") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Wrote {len(all_entries)} entries to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
