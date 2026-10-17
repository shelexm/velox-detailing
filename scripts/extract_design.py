"""Unpack the Claude Design HTML bundles from design-reference/ into readable files.

The original bundles are never modified. Each bundle holds nested artboard pages,
and each artboard holds its own manifest of base64 (optionally gzip) assets.
This script writes:

    design-reference/extracted/assets/<sha256-16>.<ext>   deduplicated assets
    design-reference/extracted/<slug>.html                 one file per artboard
    design-reference/extracted/manifest.json               asset and artboard index
    design-reference/extracted/index.html                  links to every artboard

Run it isolated from the current directory:  python -I scripts/extract_design.py
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "design-reference"
OUT_DIR = SOURCE_DIR / "extracted"
ASSET_DIR = OUT_DIR / "assets"

# Artboard slugs in the order they appear in each bundle's page_order.
SLUGS = {
    "1.html": ["design-system", "motion-spec"],
    "2.html": ["landing-desktop-1", "service-detail", "booking-form-states", "landing-desktop-2"],
    "3.html": ["mobile-1", "mobile-2", "mobile-nav", "mobile-booking-states"],
    "4.html": [
        "admin-dashboard",
        "admin-bookings",
        "admin-schedule",
        "admin-services",
        "admin-masters",
        "admin-slots",
        "admin-clients",
        "admin-mobile",
    ],
    "5.html": [
        "bot-start",
        "bot-calendar-contacts",
        "bot-integration",
        "bot-my-bookings",
        "bot-admin-notifications",
    ],
}

EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/svg+xml": "svg",
    "image/webp": "webp",
    "font/woff2": "woff2",
    "font/woff": "woff",
    "text/javascript": "js",
    "application/javascript": "js",
    "text/css": "css",
}


def script_block(document: str, kind: str) -> str | None:
    match = re.search(r'<script type="__bundler/%s">(.*?)</script>' % re.escape(kind), document, re.S)
    return match.group(1) if match else None


def decode(entry: dict) -> bytes:
    raw = base64.b64decode(entry["data"])
    return gzip.decompress(raw) if entry.get("compressed") else raw


def board_frames(outer_template: str) -> list[dict]:
    """Read board titles and frame sizes from the outer canvas template."""
    frames = []
    pattern = re.compile(
        r'<h2>(.*?)</h2><iframe src="about:blank#([0-9a-f-]{36})"[^>]*width="(\d+)" height="(\d+)"',
        re.S,
    )
    for title, uuid, width, height in pattern.findall(outer_template):
        frames.append({"uuid": uuid, "title": html.unescape(title), "width": int(width), "height": int(height)})
    return frames


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    assets: dict[str, dict] = {}
    boards: list[dict] = []

    for bundle_name, slugs in SLUGS.items():
        outer = (SOURCE_DIR / bundle_name).read_text(encoding="utf-8")
        outer_manifest = json.loads(script_block(outer, "manifest"))
        page_order = json.loads(script_block(outer, "page_order"))
        frames = {f["uuid"]: f for f in board_frames(json.loads(script_block(outer, "template")))}
        if len(page_order) != len(slugs):
            print(f"{bundle_name}: expected {len(slugs)} artboards, found {len(page_order)}", file=sys.stderr)
            return 1

        for index, (page_uuid, slug) in enumerate(zip(page_order, slugs, strict=True)):
            page = decode(outer_manifest[page_uuid]).decode("utf-8")
            manifest = json.loads(script_block(page, "manifest"))
            ext_resources = json.loads(script_block(page, "ext_resources") or "[]")
            template = json.loads(script_block(page, "template"))

            uuid_to_file: dict[str, str] = {}
            used_assets = []
            for uuid, entry in manifest.items():
                data = decode(entry)
                digest = hashlib.sha256(data).hexdigest()
                ext = EXTENSIONS.get(entry["mime"], "bin")
                filename = f"{digest[:16]}.{ext}"
                target = ASSET_DIR / filename
                if not target.exists():
                    target.write_bytes(data)
                info = assets.setdefault(
                    filename,
                    {"file": f"assets/{filename}", "mime": entry["mime"], "bytes": len(data), "sha256": digest, "used_in": []},
                )
                if slug not in info["used_in"]:
                    info["used_in"].append(slug)
                uuid_to_file[uuid] = f"assets/{filename}"
                used_assets.append(filename)

            for uuid, path in uuid_to_file.items():
                template = template.replace(uuid, path)

            resource_map = {item["id"]: uuid_to_file[item["uuid"]] for item in ext_resources if item["uuid"] in uuid_to_file}
            resource_script = "<script>window.__resources = " + json.dumps(resource_map) + ";</script>"
            head = re.search(r"<head[^>]*>", template, re.I)
            if head:
                template = template[: head.end()] + resource_script + template[head.end() :]

            title_match = re.search(r"<title>(.*?)</title>", template, re.S)
            frame = frames.get(page_uuid, {})
            (OUT_DIR / f"{slug}.html").write_text(template, encoding="utf-8", newline="\n")
            boards.append(
                {
                    "slug": slug,
                    "file": f"{slug}.html",
                    "source": f"{bundle_name}#{index}",
                    "board_title": frame.get("title"),
                    "page_title": html.unescape(title_match.group(1)) if title_match else None,
                    "width": frame.get("width"),
                    "height": frame.get("height"),
                    "assets": sorted(set(used_assets)),
                    "external_resources": [item["id"] for item in ext_resources],
                }
            )

    (OUT_DIR / "manifest.json").write_text(
        json.dumps({"boards": boards, "assets": dict(sorted(assets.items()))}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    links = "\n".join(
        f'<li><a href="{b["file"]}">{html.escape(b["board_title"] or b["slug"])}</a> '
        f'<small>{b["source"]}, {b["width"]}x{b["height"]}</small></li>'
        for b in boards
    )
    (OUT_DIR / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>VELOX design boards</title>'
        f"<h1>VELOX design boards</h1><ol>{links}</ol>\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"boards: {len(boards)}, unique assets: {len(assets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
