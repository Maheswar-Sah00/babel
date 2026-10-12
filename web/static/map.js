// The world map: D3 (vendored, window.d3) draws Natural Earth country outlines in SVG with an equal-area projection,
// so no country looks bigger than it is. Zoom and pan with the mouse, touch, the +/- buttons or the keyboard; hover
// shows a tooltip (pointer devices only); click or Enter on the country list selects. Nothing here invents a
// coordinate: countries are coloured as whole shapes, never with pins. Zooming onto a country (from the list, or
// zooming in until the country under the wheel, or in the middle, fills the view) opens its street map (static/streets.js); zooming out
// of it, or "World", comes back.

import { HATCH, palette } from "./mapdata.js";
import { createStreetMap } from "./streets.js";
import { reducedMotion } from "./ui.js";

const d3 = window.d3;
const WIDTH = 960;
const MAX_ZOOM = 8;

/** Colour the no-score pattern of a map (a d3 selection of its svg) with a theme's hatch {fill, stroke}. */
function inkHatch(sel, ink) {
  sel.select("pattern rect").attr("fill", ink.fill);
  sel.select("pattern line").attr("stroke", ink.stroke);
}

/**
 * createWorldMap(svgHost, { onSelect(cc), onHover(cc, event) | onHover(null), theme }) -> controller.
 * draw(world) once with the GeoJSON; then paint(fn), select(cc), highlight(codes, alt), zoomBy(k), reset(),
 * zoomTo(cc), pan(dx, dy), setTheme(theme), snapshot(fn, theme). While a country's street map is open, zoom and
 * pan move it instead; the canvas's data-streets holds its code.
 */
export function createWorldMap(host, { onSelect, onHover, theme = "light" }) {
  let features = new Map();
  let zoomG;
  let height = 480;
  let path;
  let projection;
  let fillOf = null;
  let selected = null;
  let startK = 1;
  let stepping = false;  // a zoom step from the buttons or keys (the user's, like a wheel or a pinch)
  let wheelCc = null;  // the country under the pointer at the last wheel event
  let colors = palette(theme);
  const canvas = host.closest(".map-canvas") || host;
  const svg = d3.select(host).append("svg").attr("class", "map-svg").attr("aria-hidden", "true")
    .attr("focusable", "false");
  const defs = svg.append("defs");
  const hatch = defs.append("pattern").attr("id", "map-hatch").attr("patternUnits", "userSpaceOnUse")
    .attr("width", 6).attr("height", 6).attr("patternTransform", "rotate(45)");
  hatch.append("rect").attr("width", 6).attr("height", 6);
  hatch.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 6).attr("stroke-width", 1.4);
  inkHatch(svg, colors.hatch);
  const zoom = d3.zoom().scaleExtent([1, MAX_ZOOM]).on("start", (e) => { startK = e.transform.k; }).on("zoom", (e) => {
    zoomG?.attr("transform", e.transform);
    canvas.dataset.zoom = e.transform.k.toFixed(2);
  }).on("end", (e) => {
    const byUser = stepping || Boolean(e.sourceEvent);
    stepping = false;
    if (byUser && !streets.cc() && e.transform.k > startK + 1e-6) {
      const cc = e.sourceEvent?.type === "wheel" ? wheelCc : centreCountry() || (inView(selected) ? selected : null);
      if (cc && e.transform.k >= fitScale(cc) - 1e-6) enterStreets(cc);
    }
  });
  const streets = createStreetMap(host, { theme, onExit: leaveStreets });

  function draw(world) {
    const shapes = world.features;
    projection = d3.geoEqualEarth().fitWidth(WIDTH - 16, { type: "FeatureCollection", features: shapes });
    path = d3.geoPath(projection);
    const [[, y0], [, y1]] = path.bounds({ type: "FeatureCollection", features: shapes });
    height = Math.ceil(y1 - y0 + 16);
    projection.translate([projection.translate()[0] + 8, projection.translate()[1] - y0 + 8]);
    svg.attr("viewBox", `0 0 ${WIDTH} ${height}`);
    zoom.extent([[0, 0], [WIDTH, height]]).translateExtent([[0, 0], [WIDTH, height]]);
    zoomG = svg.append("g").attr("class", "map-zoom");
    zoomG.append("g").attr("class", "map-countries").selectAll("path").data(shapes).join("path")
      .attr("d", path).attr("class", (f) => (f.id ? "country" : "country is-unknown"))
      .attr("data-cc", (f) => f.id || null).attr("fill", colors.notCounted);
    zoomG.append("g").attr("class", "map-outlines");
    features = new Map(shapes.filter((f) => f.id).map((f) => [f.id, f]));
    const countries = zoomG.select(".map-countries");
    countries.on("pointermove", (e) => {
      const cc = e.target.dataset?.cc;
      if (e.pointerType === "touch" || !cc) return onHover(null);
      onHover(cc, e);
    }).on("pointerleave", () => onHover(null)).on("click", (e) => {
      const cc = e.target.dataset?.cc;
      if (cc) onSelect(cc);
    });
    svg.call(zoom).on("dblclick.zoom", null);
    // at the limit d3 ignores the wheel; capture, since mid-gesture it stops the event before other listeners
    svg.node().addEventListener("wheel", (e) => {
      wheelCc = e.target.dataset?.cc || null;
      if (e.deltaY < 0 && atMaxZoom() && !streets.cc()) enterStreets(wheelCc || centreCountry());
    }, { capture: true, passive: true });
  }

  const atMaxZoom = () => d3.zoomTransform(svg.node()).k >= MAX_ZOOM - 1e-6;

  /** The country at the centre of the view (null over the sea). */
  function centreCountry() {
    const p = projection.invert(d3.zoomTransform(svg.node()).invert([WIDTH / 2, height / 2]));
    for (const [cc, f] of features) if (d3.geoContains(f, p)) return cc;
    return null;
  }

  /** Whether any of a country's bounding box is in the view. */
  function inView(cc) {
    if (!features.has(cc)) return false;
    const t = d3.zoomTransform(svg.node());
    const [[x0, y0], [x1, y1]] = path.bounds(features.get(cc));
    const [[vx0, vy0], [vx1, vy1]] = [t.invert([0, 0]), t.invert([WIDTH, height])];
    return x0 < vx1 && x1 > vx0 && y0 < vy1 && y1 > vy0;
  }

  /** The zoom at which a country fills most of the view (very large or scattered ones: less). */
  function fitScale(cc) {
    const [[x0, y0], [x1, y1]] = path.bounds(features.get(cc));
    return Math.max(1, Math.min(MAX_ZOOM, 0.7 / Math.max((x1 - x0) / WIDTH, (y1 - y0) / height)));
  }

  function openStreets(cc) {
    streets.open(features.get(cc), fillOf?.(cc).fill);
    canvas.dataset.streets = cc;
  }

  function closeStreets() {
    streets.close();
    delete canvas.dataset.streets;
  }

  /** Zoomed in onto a country by the user: its street map, and the country gets selected. */
  function enterStreets(cc) {
    if (!cc) return;
    openStreets(cc);
    onSelect(cc);
  }

  /** Zooming out of a street map: back to the world map, still on that country. */
  function leaveStreets() {
    const cc = streets.cc();
    closeStreets();
    if (cc) worldTo(cc);
  }

  /** fn(cc) -> {fill}: colours every country (unknown shapes stay hatched). */
  function paint(fn) {
    fillOf = fn;
    zoomG?.selectAll(".country").attr("fill", (f) => (f.id ? fn(f.id).fill : HATCH));
    if (streets.cc()) streets.setFill(fn(streets.cc()).fill);
  }

  /** Use a theme's hatch colours (the caller repaints the fills with the same theme). */
  function setTheme(next) {
    colors = palette(next);
    inkHatch(svg, colors.hatch);
    streets.setTheme(next);
  }

  /** A detached copy of the map painted with fn(cc) -> {fill} and a theme's hatch (the live map is untouched). */
  function snapshot(fn, copyTheme) {
    const copy = svg.node().cloneNode(true);
    for (const p of copy.querySelectorAll("path.country[data-cc]")) p.setAttribute("fill", fn(p.dataset.cc).fill);
    inkHatch(d3.select(copy), palette(copyTheme).hatch);
    return copy;
  }

  function outline(codes, cls) {
    const g = zoomG?.select(".map-outlines");
    if (!g) return;
    g.selectAll(`path.${cls}`).data(codes.filter((cc) => features.has(cc)), (cc) => cc).join("path")
      .attr("class", cls).attr("d", (cc) => path(features.get(cc)));
  }

  /** Outline the selected country (null clears); a street map of another country closes. */
  function select(cc) {
    selected = cc;
    if (streets.cc() && streets.cc() !== cc) closeStreets();
    outline(cc ? [cc] : [], "outline-selected");
  }

  /** Emphasise some countries and fade the rest; alt = a second set drawn with a dashed outline. null clears. */
  function highlight(codes, alt = []) {
    const on = codes ? new Set([...codes, ...alt]) : null;
    if (on) closeStreets();  // the highlight is on the world map
    zoomG?.selectAll(".country").classed("is-dim", (f) => Boolean(on) && !on.has(f.id));
    outline(codes || [], "outline-highlight");
    outline(codes ? alt : [], "outline-alt");
  }

  const run = (fn) => (reducedMotion() ? svg.call(fn) : svg.transition().duration(350).call(fn));
  function zoomBy(k) {
    if (streets.cc()) return streets.zoomBy(k);
    if (k > 1 && atMaxZoom()) return enterStreets(centreCountry() || (inView(selected) ? selected : null));
    stepping = true;
    run((s) => zoom.scaleBy(s, k));
  }
  function reset() {
    closeStreets();
    run((s) => zoom.transform(s, d3.zoomIdentity));
  }
  function pan(dx, dy) {
    if (streets.cc()) return streets.pan(dx, dy);
    svg.call(zoom.translateBy, dx / d3.zoomTransform(svg.node()).k, dy / d3.zoomTransform(svg.node()).k);
  }

  /** Zoom onto a country: the world map zooms to it, then its street map opens. */
  function zoomTo(cc) {
    if (!features.has(cc)) return;
    worldTo(cc);
    openStreets(cc);
  }

  /** Zoom the world map so a country fills most of the view (very large or scattered ones zoom out). */
  function worldTo(cc) {
    const f = features.get(cc);
    if (!f) return;
    const [[x0, y0], [x1, y1]] = path.bounds(f);
    const k = fitScale(cc);
    const t = d3.zoomIdentity.translate(WIDTH / 2, height / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    run((s) => zoom.transform(s, t));
  }

  return { draw, paint, select, highlight, zoomBy, reset, pan, zoomTo, setTheme, snapshot,
    has: (cc) => features.has(cc), nameOf: (cc) => features.get(cc)?.properties?.name };
}
