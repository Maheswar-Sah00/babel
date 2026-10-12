"""Country boundaries for the Plan screen's map -> web/static/world.json (committed; run again only to update it).
With --hero: the Start screen's dot-matrix world -> web/static/world-hero.json, from the finer 1:50m outlines, ids
only, with points closer than 0.3 degree dropped (about a pixel there, far finer than its dots); islands too small to
keep a shape are kept as single points ("islands": [lon, lat, country id]), so each still gets its dot.

Source: Natural Earth 1:110m (or 1:50m) admin-0 countries (public domain, naturalearthdata.com), pinned to v5.1.2.
Kept: an ISO 3166-1 alpha-2 id per country (ISO_A2_EH, which fixes Natural Earth's '-99' for France and Norway;
'' where none exists), its name and its outline. Antarctica is dropped (no Qloo data). Coordinates are rounded to
0.01 degree, well inside the precision of a 1:110m map, and rings are wound the way d3-geo expects (outer rings
clockwise, holes anticlockwise), so no polygon is drawn inside-out.

  python tools/build_world.py            # web/static/world.json
  python tools/build_world.py --hero     # web/static/world-hero.json
"""
import argparse
import hashlib
import math
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/"
       "ne_{scale}_admin_0_countries.geojson")
OUT = ROOT / "web" / "static" / "world.json"
HERO = ROOT / "web" / "static" / "world-hero.json"


def area(ring):
    """Signed planar area (shoelace); positive = anticlockwise with north up."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2


def thin(ring, tolerance):
    """Drop points closer than `tolerance` degrees to the last kept one (the ring's last point always stays)."""
    if not tolerance:
        return ring
    out = [ring[0]]
    for point in ring[1:-1]:
        if math.dist(point, out[-1]) >= tolerance:
            out.append(point)
    return out + [ring[-1]]


def clean(ring, outer, tolerance=0):
    """Rounded, without repeated points, closed, and wound for d3-geo; None if too small to draw."""
    out = []
    for x, y in thin(ring, tolerance):
        point = [round(x, 2), round(y, 2)]
        if not out or point != out[-1]:
            out.append(point)
    if out[0] != out[-1]:
        out.append(out[0])
    if len(out) < 4 or area(out) == 0:
        return None
    return out[::-1] if (area(out) > 0) == outer else out


def polygons(geometry, tolerance=0, dropped=None):
    """The geometry's polygons, cleaned; the centre of each one too small to keep goes to `dropped` (if given)."""
    rings = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    out = []
    for poly in rings:
        shell = clean(poly[0], True, tolerance)
        if shell:
            out.append([shell] + [h for h in (clean(r, False, tolerance) for r in poly[1:]) if h])
        elif dropped is not None and len(poly[0]) >= 4:
            xs, ys = zip(*poly[0][:-1])
            dropped.append([round(sum(xs) / len(xs), 2), round(sum(ys) / len(ys), 2)])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hero", action="store_true", help="build the Start screen's finer outlines instead")
    hero = ap.parse_args().hero
    scale, out, tolerance = ("50m", HERO, 0.3) if hero else ("110m", OUT, 0)
    resp = requests.get(URL.format(scale=scale), timeout=120)
    resp.raise_for_status()
    features, islands = [], []
    for f in resp.json()["features"]:
        p = f["properties"]
        code = next((c for c in (p.get("ISO_A2_EH"), p.get("ISO_A2")) if c and c != "-99"), "")
        if code == "AQ":
            continue
        dropped = [] if hero else None
        polys = polygons(f["geometry"], tolerance, dropped)
        islands += [[x, y, code] for x, y in dropped or []]
        if not polys:
            continue
        geometry = ({"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else
                    {"type": "MultiPolygon", "coordinates": polys})
        features.append({"type": "Feature", "id": code, "properties": {} if hero else {"name": p["NAME"]},
                         "geometry": geometry})
    features.sort(key=lambda f: (f["id"] == "", f["id"], f["properties"].get("name", "")))
    data = {"type": "FeatureCollection",
            "source": f"Natural Earth 1:{scale} admin-0 countries v5.1.2 (public domain), simplified by "
                      "tools/build_world.py", "features": features}
    if hero:
        data["islands"] = sorted(islands, key=lambda i: (i[2], i[0], i[1]))
    out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: {len(features)} countries, {len(islands)} small islands as points, "
          f"{out.stat().st_size / 1024:.0f} KB; source sha256 "
          f"{hashlib.sha256(resp.content).hexdigest()[:16]}")


if __name__ == "__main__":
    main()
