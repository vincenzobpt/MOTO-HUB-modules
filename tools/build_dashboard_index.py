#!/usr/bin/env python3
"""Validate every dashboard under dashboards/files/ and write dashboards/index.json.

Usage:
    python3 tools/build_dashboard_index.py           # validate, extract previews, write the index
    python3 tools/build_dashboard_index.py --check   # validate only, exit 1 on any problem

Everything the app filters on - resolution, orientation, map engine, whether an OBD adapter or a
module is needed, which elements are on it - is read from the file's own dashboard.json, never
typed by hand, so a filter cannot promise what the dashboard does not do. The only hand-written
part is dashboards/listing.json: the kind of dashboard, a few tags, and whether it is featured.

The rules mirror what MOTO-HUB accepts at import (DashboardPackage.read, DashboardLibrary.importBytes,
DashboardEngine.sourceFor/usesObd). The app still validates whatever it downloads: this index only
advertises, and a file that fails here would only have been refused on the phone.
"""
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS = ROOT / "dashboards"
FILES = DASHBOARDS / "files"
PREVIEWS = DASHBOARDS / "previews"
LISTING = DASHBOARDS / "listing.json"
INDEX = DASHBOARDS / "index.json"

ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
VERSION = re.compile(r"^[0-9][0-9A-Za-z.\-]{0,15}$")
KINDS = {"ride", "touring", "engine", "track", "minimal"}
TAG = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_DOCUMENT_BYTES = 512 * 1024
MAX_PREVIEW_BYTES = 1024 * 1024
MAX_ENTRIES = 64
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Built-in dashboards ship with the app; the app refuses a file that takes one of their ids.
RESERVED_PREFIX = "motohub."

MAP_ELEMENTS = {
    "map.osm": "osm",
    "map.maplibre": "maplibre",
    "map.pov3d": "pov3d",
    "map.projection": "projection",
}
RIDE_SCENE_SOURCES = {"osm": "osm", "maplibre": "maplibre", "pov3d": "pov3d", "projection": "projection"}


def flatten(elements):
    for element in elements or []:
        yield element
        yield from flatten(element.get("children"))


def all_elements(document):
    top = list(document.get("elements") or [])
    for variant in document.get("variants") or []:
        top.extend(variant.get("elements") or [])
    return list(flatten(top))


def engine_of(document):
    """DashboardEngine.sourceFor: the first map element decides; no map means the OBD session."""
    elements = all_elements(document)
    for element in elements:
        if element.get("type") == "scene.ride":
            props = element.get("props") or {}
            return RIDE_SCENE_SOURCES.get(props.get("mapSource", "rider"), "osm")
    for element in elements:
        engine = MAP_ELEMENTS.get(element.get("type"))
        if engine:
            return engine
    return "obd"


def uses_obd(document):
    """DashboardEngine.usesObd."""
    if (document.get("requires") or {}).get("obd"):
        return True
    for element in all_elements(document):
        kind = element.get("type", "")
        props = element.get("props") or {}
        if kind.startswith("scene.obd.") or kind in ("signal.leds", "signal.gear"):
            return True
        if str(props.get("signal", "")).startswith("obd."):
            return True
        if "obd." in str(element.get("visibleWhen") or "") or "obd." in str(props.get("when", "")):
            return True
    return False


def needs_module(document):
    requires = document.get("requires") or {}
    if requires.get("module"):
        return requires["module"]
    for element in all_elements(document):
        props = element.get("props") or {}
        if element.get("type") == "map.projection" or props.get("mapSource") == "projection":
            return "projection"
    return None


def orientations(document):
    canvas = document["canvas"]
    found = {"portrait" if canvas["height"] > canvas["width"] else "landscape"}
    for variant in document.get("variants") or []:
        when = variant.get("when", "any")
        if when in ("landscape", "portrait"):
            found.add(when)
        else:
            c = variant.get("canvas") or canvas
            found.add("portrait" if c["height"] > c["width"] else "landscape")
    return sorted(found)


def read_package(path, problems):
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        problems.append(f"{path.name}: larger than 4 MB")
        return None, None, data
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        problems.append(f"{path.name}: not a .mhd (zip) file")
        return None, None, data
    names = [info for info in archive.infolist() if not info.is_dir()]
    if len(names) > MAX_ENTRIES:
        problems.append(f"{path.name}: too many files inside")
        return None, None, data
    document = preview = None
    for info in names:
        if info.filename == "dashboard.json":
            if info.file_size > MAX_DOCUMENT_BYTES:
                problems.append(f"{path.name}: dashboard.json is larger than 512 KB")
                return None, None, data
            try:
                document = json.loads(archive.read(info).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                problems.append(f"{path.name}: dashboard.json is not valid JSON ({error})")
                return None, None, data
        elif info.filename == "preview.png":
            if info.file_size > MAX_PREVIEW_BYTES:
                problems.append(f"{path.name}: preview.png is larger than 1 MB")
                return None, None, data
            preview = archive.read(info)
    if document is None:
        problems.append(f"{path.name}: no dashboard.json inside")
    return document, preview, data


def git_dates(path):
    """First and last commit dates of a file; today for a file not committed yet."""
    def run(*args):
        try:
            out = subprocess.run(["git", "log", *args, "--format=%cs", "--", str(path)],
                                 cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
            return out
        except (OSError, subprocess.CalledProcessError):
            return []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = run("--follow")
    return (history[-1] if history else today), (history[0] if history else today)


def main():
    check_only = "--check" in sys.argv[1:]
    problems = []
    listing = {}
    if LISTING.exists():
        try:
            listing = json.loads(LISTING.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            problems.append(f"listing.json is not valid JSON ({error})")

    entries = []
    seen = set()
    for path in sorted(FILES.glob("*")):
        if path.name.startswith("."):
            continue
        if path.suffix != ".mhd":
            problems.append(f"{path.name}: only .mhd files belong in dashboards/files/")
            continue
        document, preview, data = read_package(path, problems)
        if document is None:
            continue
        name = path.name
        dash_id = str(document.get("id", ""))
        if not ID.match(dash_id):
            problems.append(f"{name}: id \"{dash_id}\" must be 3-64 of a-z 0-9 . _ -")
            continue
        if dash_id.startswith(RESERVED_PREFIX):
            problems.append(f"{name}: ids starting with \"{RESERVED_PREFIX}\" belong to MOTO-HUB's built-ins")
            continue
        if path.stem != dash_id:
            problems.append(f"{name}: the file must be named after its id ({dash_id}.mhd)")
            continue
        if dash_id in seen:
            problems.append(f"{name}: id {dash_id} is listed twice")
            continue
        seen.add(dash_id)
        # The app reads a missing schema as 1 (DashboardDocument.schema defaults to it).
        if document.get("schema", 1) != 1:
            problems.append(f"{name}: schema must be 1")
            continue
        canvas = document.get("canvas") or {}
        if not all(isinstance(canvas.get(k), int) and 64 <= canvas[k] <= 4096 for k in ("width", "height")):
            problems.append(f"{name}: canvas width/height must be whole numbers between 64 and 4096")
            continue
        if not str(document.get("name", "")).strip():
            problems.append(f"{name}: the dashboard has no name")
            continue
        if not str(document.get("author", "")).strip():
            problems.append(f"{name}: the dashboard has no author")
            continue
        version = str(document.get("version", "1"))
        if not VERSION.match(version):
            problems.append(f"{name}: version \"{version}\" must start with a digit")
            continue
        if preview is None or not preview.startswith(PNG_MAGIC):
            problems.append(f"{name}: needs a preview.png (export it from the Dashboard Editor)")
            continue

        extra = listing.get(dash_id, {})
        kind = extra.get("kind", "ride")
        if kind not in KINDS:
            problems.append(f"listing.json {dash_id}: kind must be one of {sorted(KINDS)}")
            continue
        tags = extra.get("tags", [])
        if not isinstance(tags, list) or len(tags) > 6 or not all(isinstance(t, str) and TAG.match(t) for t in tags):
            problems.append(f"listing.json {dash_id}: up to 6 lowercase tags")
            continue

        published, updated = git_dates(path)
        requires = document.get("requires") or {}
        elements = sorted({e.get("type", "") for e in all_elements(document) if e.get("type")})
        entries.append({
            "id": dash_id,
            "name": document["name"].strip(),
            "author": document["author"].strip(),
            "description": str(document.get("description", "")).strip(),
            "version": version,
            "kind": kind,
            "tags": tags,
            "featured": bool(extra.get("featured", False)),
            "published": published,
            "updated": updated,
            "engine": engine_of(document),
            "canvas": {"width": canvas["width"], "height": canvas["height"]},
            "orientations": orientations(document),
            "requires": {
                "obd": uses_obd(document),
                "module": needs_module(document),
                "app": requires.get("app"),
            },
            "elements": elements,
            "path": f"dashboards/files/{name}",
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "preview": f"dashboards/previews/{dash_id}.png",
            "previewSha256": hashlib.sha256(preview).hexdigest(),
        })
        if not check_only:
            PREVIEWS.mkdir(parents=True, exist_ok=True)
            (PREVIEWS / f"{dash_id}.png").write_bytes(preview)

    for dash_id in listing:
        if dash_id not in seen and not any(p.startswith(f"{dash_id}.mhd") for p in problems):
            problems.append(f"listing.json: {dash_id} has no file in dashboards/files/")

    if problems:
        print("Problems:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    if check_only:
        print(f"{len(entries)} dashboard(s) valid.")
        return 0

    # Previews of dashboards that are gone go with them.
    if PREVIEWS.exists():
        for stale in PREVIEWS.glob("*.png"):
            if stale.stem not in seen:
                stale.unlink()
    entries.sort(key=lambda e: (not e["featured"], e["name"].lower()))
    index = {"schema": 1, "dashboards": entries}
    text = json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    if not INDEX.exists() or INDEX.read_text(encoding="utf-8") != text:
        INDEX.write_text(text, encoding="utf-8")
    print(f"Wrote {INDEX.relative_to(ROOT)} with {len(entries)} dashboard(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
