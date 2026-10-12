// The street map of one country: when the world map zooms onto a country, OpenStreetMap's standard raster tiles (Web
// Mercator) cover the map area, down to street level, with the country's outline in its map colour on top and the
// rest of the world dimmed; close in, the coarse 1:110m outline fades and the tiles' own borders take over. Context
// only: Babel's figures are per country, and nothing here places data inside one. Tiles load straight from
// tile.openstreetmap.org (the page's CSP allows their images; light use with attribution, as its tile policy asks;
// the tile requests send the site's origin as referrer, which the policy needs). The dark theme shows them grey and
// inverted (CSS). If none load, the outline still shows, with a note.

import { HATCH } from "./mapdata.js";
import { h, reducedMotion } from "./ui.js";

const d3 = window.d3;
const TAU = 2 * Math.PI;
const TILE = 256;
const MAX_Z = 19;
const NEAR_MAINLAND = 0.25;  // fit the view to the polygons at least this share of the country's largest one
const CLOSE = 6;  // zoomed in this many times past the country's whole view, the outline and the dimming fade

const tileUrl = ({ z, col, row }) => `https://tile.openstreetmap.org/${z}/${(col % 2 ** z + 2 ** z) % 2 ** z}/${row}.png`;

/** Bounds in unit Web Mercator (the world is 1 wide, centred on 0) of the country's main polygons: far islands and
 * overseas parts are left out, and so is anything that would wrap round the antimeridian. */
function mainBounds(feature) {
  const unit = d3.geoPath(d3.geoMercator().scale(1 / TAU).translate([0, 0]));
  const g = feature.geometry;
  const parts = g.type === "MultiPolygon" ? g.coordinates.map((c) => ({ type: "Polygon", coordinates: c })) : [g];
  const areas = parts.map((p) => d3.geoArea(p));
  const largest = parts[areas.indexOf(Math.max(...areas))];
  const near = { type: "GeometryCollection", geometries: parts.filter((p, i) => areas[i] >= NEAR_MAINLAND * Math.max(...areas)) };
  const b = unit.bounds(near);
  return b[1][0] - b[0][0] > 0.5 ? unit.bounds(largest) : b;
}

/**
 * createStreetMap(host, { theme, onExit }) -> controller over a layer that covers host.
 * open(feature, fill), close(), setFill(fill), setTheme(theme), zoomBy(k), pan(dx, dy); cc() is the open country.
 * onExit() runs when the user zooms out past the country's whole view (back to the world map).
 */
export function createStreetMap(host, { theme = "light", onExit }) {
  let feature = null;
  let current = d3.zoomIdentity;
  let fitK = TILE;
  let minK = TILE;
  let loaded = 0;
  let failed = 0;
  const tiles = h("div", { class: "streets-tiles" });
  const note = h("p", { class: "streets-note" });
  const credit = h("p", { class: "streets-credit" }, "© ",
    h("a", { href: "https://www.openstreetmap.org/copyright", target: "_blank", rel: "noopener" }, "OpenStreetMap"),
    " contributors");
  const layer = h("div", { class: "map-streets", hidden: true, "data-theme": theme }, tiles);
  host.append(layer);
  const svg = d3.select(layer).append("svg").attr("class", "streets-svg").attr("aria-hidden", "true");
  const mask = svg.append("path").attr("class", "streets-mask");
  const halo = svg.append("path").attr("class", "streets-halo");  // a dark edge: pale outline colours show on the tiles
  const edge = svg.append("path").attr("class", "streets-outline");
  layer.append(note, credit);
  const projection = d3.geoMercator();
  const path = d3.geoPath(projection);
  const size = () => [layer.clientWidth || 1, layer.clientHeight || 1];

  const zoom = d3.zoom().extent(() => [[0, 0], size()]).translateExtent([[-Infinity, -0.5], [Infinity, 0.5]])  // wraps east-west
    .on("zoom", (e) => render(e.transform));
  d3.select(layer).call(zoom);
  layer.addEventListener("wheel", (e) => {
    if (feature && e.deltaY > 0 && current.k <= minK * 1.001) onExit?.();
  }, { passive: true });
  new ResizeObserver(() => feature && render(current)).observe(layer);

  function status() {
    layer.dataset.tiles = loaded ? "ok" : failed ? "failed" : "loading";
    note.textContent = loaded || !failed
      ? "Street map for context: Babel's figures are for the whole country."
      : "The street map could not load; the outline shows the country. Babel's figures are for the whole country.";
  }

  /** Draw the tiles that cover the view at transform t, and the outline and mask. */
  function render(t) {
    current = t;
    const [w, hgt] = size();
    const z = Math.max(0, Math.min(MAX_Z, Math.round(Math.log2(t.k / TILE))));
    const n = 2 ** z;
    const side = t.k / n;
    const x0 = t.x - t.k / 2;
    const y0 = t.y - t.k / 2;
    const list = [];
    for (let row = Math.max(0, Math.floor(-y0 / side)); row <= Math.min(n - 1, Math.floor((hgt - y0) / side)); row++) {
      for (let col = Math.floor(-x0 / side); col <= Math.floor((w - x0) / side); col++) {
        list.push({ z, col, row, key: `${z}/${col}/${row}`, url: tileUrl({ z, col, row }) });
      }
    }
    d3.select(tiles).selectAll("img").data(list, (d) => d.key).join((enter) => enter.append("img")
      .attr("alt", "").attr("draggable", "false").attr("decoding", "async")
      .attr("referrerpolicy", "strict-origin-when-cross-origin")  // the page sends none; OSM's tile servers need it
      .on("load", () => { loaded++; status(); }).on("error", function () { this.classList.add("is-failed"); failed++; status(); })
      .attr("src", (d) => d.url))
      .style("left", (d) => `${x0 + d.col * side}px`).style("top", (d) => `${y0 + d.row * side}px`)
      .style("width", `${side + 0.5}px`).style("height", `${side + 0.5}px`);
    projection.scale(t.k / TAU).translate([t.x, t.y]).clipExtent([[-w, -hgt], [2 * w, 2 * hgt]]);
    const shape = path(feature) || "";
    svg.attr("viewBox", `0 0 ${w} ${hgt}`);
    halo.attr("d", shape);
    edge.attr("d", shape);
    mask.attr("d", `M${-w},${-hgt}H${2 * w}V${2 * hgt}H${-w}Z${shape}`);
    layer.classList.toggle("is-close", t.k > fitK * CLOSE);
  }

  /** Show the street map of a country (a GeoJSON feature), its outline in the map's fill for it. */
  function open(f, fill) {
    feature = f;
    loaded = failed = 0;
    tiles.replaceChildren();
    layer.hidden = false;
    setFill(fill);
    status();
    const [w, hgt] = size();
    const [[x0, y0], [x1, y1]] = mainBounds(f);
    const k = Math.min(TILE * 2 ** MAX_Z, Math.max(TILE * 2, 0.8 / Math.max((x1 - x0) / w, (y1 - y0) / hgt, 1e-12)));
    fitK = k;
    minK = Math.max(TILE * 2, k / 4);
    zoom.scaleExtent([minK, TILE * 2 ** MAX_Z]);
    d3.select(layer).call(zoom.transform, d3.zoomIdentity.translate(w / 2 - k * (x0 + x1) / 2, hgt / 2 - k * (y0 + y1) / 2).scale(k));
  }

  function close() {
    feature = null;
    layer.hidden = true;
    tiles.replaceChildren();  // stops tiles still loading
  }

  /** The outline's colour: the country's map fill (the no-score hatch gets the default ink). */
  function setFill(fill) {
    edge.style("stroke", fill && fill !== HATCH ? fill : null);
  }

  /** The tiles' look for a theme (dark: grey and inverted, in CSS). */
  function setTheme(next) {
    layer.dataset.theme = next;
  }

  const run = (fn) => (reducedMotion() ? d3.select(layer).call(fn) : d3.select(layer).transition().duration(300).call(fn));
  /** Zoom by k; zooming out from the country's whole view goes back to the world map. */
  function zoomBy(k) {
    if (k < 1 && current.k <= minK * 1.001) return onExit?.();
    run((s) => zoom.scaleBy(s, k));
  }
  const pan = (dx, dy) => d3.select(layer).call(zoom.translateBy, dx / current.k, dy / current.k);

  return { open, close, setFill, setTheme, zoomBy, pan, cc: () => feature?.id || null };
}
