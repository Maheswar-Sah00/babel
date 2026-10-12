// The Start screen's backdrop: a dot-matrix world (Natural Earth 1:50m outlines from static/world-hero.json, built by
// tools/build_world.py --hero; Equal Earth projection, so no country looks bigger than it is) with the languages Babel
// plans for pinned, in their own scripts, on a country where each is spoken, plus Hindi and seven African languages.
// The dots of the countries where those languages are spoken are lit. Decorative (aria-hidden): it shows no data.
// Redrawn when the band changes size (or a card in it does) and when the theme changes.

const d3 = window.d3;

// Babel's language -> countries mapping (babel/languages.py COUNTRIES; tests/test_hero_web.py keeps them equal).
export const SPOKEN = {
  schinese: ["CN"], tchinese: ["TW", "HK", "MO"], japanese: ["JP"], koreana: ["KR"], brazilian: ["BR"],
  russian: ["RU", "BY", "KZ"], spanish: ["ES", "MX", "AR", "CO", "CL", "PE"], turkish: ["TR"],
  german: ["DE", "AT", "CH"], french: ["FR", "BE"], polish: ["PL"], italian: ["IT"], ukrainian: ["UA"], thai: ["TH"],
};
// Languages on the map that Babel does not plan for (the art only), and where they are widely spoken.
export const ALSO = {
  hindi: ["IN"], arabic: ["EG", "LY", "TN", "DZ", "MA", "SD", "MR"], hausa: ["NG", "NE"], amharic: ["ET"],
  swahili: ["TZ", "KE", "UG"], lingala: ["CD", "CG"], somali: ["SO"], zulu: ["ZA"],
};

// One chip per language, in the order they are placed when space is short: the name in its own script, its BCP 47
// tag (so the browser picks the right font), and where the marker sits as [lon, lat] near the middle of a country
// (art, not data). A later place is used when the first is under a card.
export const PINS = [
  { lang: "schinese", tag: "zh-Hans", label: "简体中文", places: [[104, 34.5]] },
  { lang: "spanish", tag: "es", label: "Español", places: [[-102, 23.5], [-3.7, 40.2]] },
  { lang: "hindi", tag: "hi", label: "हिन्दी", places: [[79, 22.5]] },
  { lang: "arabic", tag: "ar", label: "العربية", places: [[30.8, 26.8]] },
  { lang: "russian", tag: "ru", label: "Русский", places: [[96, 61], [88, 55.5]] },
  { lang: "brazilian", tag: "pt-BR", label: "Português", places: [[-51, -10], [-8, 39.6]] },
  { lang: "swahili", tag: "sw", label: "Kiswahili", places: [[35, -6.4]] },
  { lang: "japanese", tag: "ja", label: "日本語", places: [[138.5, 36.5]] },
  { lang: "german", tag: "de", label: "Deutsch", places: [[10.3, 51.1]] },
  { lang: "french", tag: "fr", label: "Français", places: [[2.5, 46.6]] },
  { lang: "hausa", tag: "ha", label: "Hausa", places: [[8.2, 11.6]] },
  { lang: "koreana", tag: "ko", label: "한국어", places: [[127.8, 36.4]] },
  { lang: "amharic", tag: "am", label: "አማርኛ", places: [[39.5, 9]] },
  { lang: "turkish", tag: "tr", label: "Türkçe", places: [[35, 39]] },
  { lang: "zulu", tag: "zu", label: "isiZulu", places: [[30.6, -28.6]] },
  { lang: "polish", tag: "pl", label: "Polski", places: [[19.3, 52.1]] },
  { lang: "italian", tag: "it", label: "Italiano", places: [[12.6, 42.8]] },
  { lang: "thai", tag: "th", label: "ไทย", places: [[101, 15.5]] },
  { lang: "lingala", tag: "ln", label: "Lingála", places: [[21.8, -2.9]] },
  { lang: "somali", tag: "so", label: "Soomaali", places: [[45.5, 5.5]] },
  { lang: "ukrainian", tag: "uk", label: "Українська", places: [[31.3, 49]] },
  { lang: "tchinese", tag: "zh-Hant", label: "繁體中文", places: [[121, 23.7]] },
];

const SVG = "http://www.w3.org/2000/svg";
const LIT = new Set([...Object.values(SPOKEN), ...Object.values(ALSO)].flat());
const NORTH = 64;   // wide layout: this latitude sits just under the game card (the Arctic goes beneath it) ...
const SOUTH = -56;  // ... and Cape Horn just above the band's bottom edge, so every continent shows whole

export function initHero() {
  const band = document.querySelector(".band");
  const canvas = band?.querySelector(".hero-map");
  if (!band || !canvas?.getContext || !d3) return;
  const leaders = band.querySelector(".hero-leaders");
  const pins = band.querySelector(".pins");
  const chips = PINS.map((pin) => {
    const chip = document.createElement("span");
    chip.className = "pin";
    chip.lang = pin.tag;
    chip.dir = "auto";
    chip.textContent = pin.label;
    chip.dataset.lang = pin.lang;
    chip.hidden = true;
    chip.addEventListener("animationend", () => chip.classList.remove("is-new"));
    pins.append(chip);
    return chip;
  });
  const view = { band, canvas, leaders, chips, world: null, key: "", shown: false };
  let frame = 0;
  const redraw = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => draw(view));
  };
  fetch("/static/world-hero.json")
    .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
    .then((world) => {
      view.world = world;
      view.lit = { type: "FeatureCollection", features: world.features.filter((f) => LIT.has(f.id)) };
      redraw();
    })
    .catch(() => { band.dataset.map = "failed"; });
  const observer = new ResizeObserver(redraw);
  for (const el of [band, band.querySelector(".game-card"), band.querySelector(".evidence-card")]) if (el) observer.observe(el);
  document.addEventListener("babel:theme", redraw);
  document.fonts?.ready.then(redraw);
}

function draw(view) {
  const { band, canvas, world } = view;
  const W = band.clientWidth;
  const H = band.clientHeight;
  if (!world || !W || !H) return;
  const style = getComputedStyle(band);
  const colors = Object.fromEntries(["dot", "lit", "glow", "grid"].map((k) => [k, style.getPropertyValue(`--hero-${k}`).trim()]));
  const game = rectIn(band, band.querySelector(".game-card"));
  const evidence = rectIn(band, band.querySelector(".evidence-card"));
  const wasHidden = view.chips.map((chip) => chip.hidden);
  for (const chip of view.chips) chip.hidden = false;  // to measure them
  const sizes = view.chips.map((chip) => [chip.offsetWidth, chip.offsetHeight]);
  const key = JSON.stringify([W, H, colors, game, evidence, sizes]);
  if (key === view.key) {
    view.chips.forEach((chip, i) => { chip.hidden = wasHidden[i]; });
    return;
  }
  view.key = key;

  const stacked = evidence && getComputedStyle(band.querySelector(".evidence-card")).position !== "absolute";
  const projection = fit(world, W, H, game, stacked ? evidence : null);
  paint(canvas, W, H, projection, world, view.lit, colors);
  const blocked = [game, stacked ? null : evidence].filter(Boolean);
  placePins(view, W, H, projection, blocked, sizes);
  band.dataset.map = "ready";
}

/** An element's box relative to the band, as [left, top, right, bottom], or null when hidden. */
function rectIn(band, el) {
  if (!el || !el.offsetParent) return null;
  const b = band.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  return [r.left - b.left, r.top - b.top, r.right - b.left, r.bottom - b.top].map(Math.round);
}

/**
 * Wide layout: latitude NORTH just under the game card and SOUTH just above the bottom edge, centred (wider than
 * the band only on very wide, short bands). Stacked layout (the evidence card below the map): the whole world fits
 * the gap between the two cards.
 */
function fit(world, W, H, game, evidenceBelow) {
  const projection = d3.geoEqualEarth();
  const top = game ? game[3] : 0;
  if (evidenceBelow) {
    return projection.fitExtent([[10, top + 14], [W - 10, Math.max(top + 60, evidenceBelow[1] - 14)]], world);
  }
  const span = projection([0, SOUTH])[1] - projection([0, NORTH])[1];  // at the default scale
  const scale = projection.scale() * Math.max(40, H - 14 - (top + 8)) / span;
  projection.scale(scale).translate([W / 2, 0]);
  return projection.translate([W / 2, top + 8 - projection([0, NORTH])[1]]);
}

function paint(canvas, W, H, projection, world, lit, colors) {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(W * ratio);
  canvas.height = Math.round(H * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const path = d3.geoPath(projection, ctx);

  ctx.beginPath();
  path(d3.geoGraticule10());
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  ctx.stroke();

  if ("filter" in ctx) {  // a soft glow under the lit countries
    ctx.save();
    ctx.filter = "blur(12px)";
    ctx.beginPath();
    path(lit);
    ctx.fillStyle = colors.glow;
    ctx.fill();
    ctx.restore();
  }

  // Land (red) and lit countries (red + green) on a 1x mask; one dot per hexagonal grid point on land, plus one dot
  // for each island too small for the grid (snapped to the nearest grid point).
  const mask = document.createElement("canvas");
  mask.width = W;
  mask.height = H;
  const m = mask.getContext("2d", { willReadFrequently: true });
  const maskPath = d3.geoPath(projection, m);
  m.fillStyle = "#f00";
  m.beginPath();
  maskPath(world);
  m.fill();
  m.fillStyle = "#ff0";
  m.beginPath();
  maskPath(lit);
  m.fill();
  const px = m.getImageData(0, 0, W, H).data;
  const gap = W < 720 ? 4.4 : 5.6;
  const r = W < 720 ? 1.15 : 1.3;
  const rowH = gap * 0.866;
  const dots = new Map();  // "row,col" -> [x, y, lit]
  for (let row = 0, y = gap / 2; y < H; row += 1, y += rowH) {
    for (let col = 0, x = row % 2 ? gap : gap / 2; x < W; col += 1, x += gap) {
      const i = (Math.floor(y) * W + Math.floor(x)) * 4;
      if (px[i] >= 128) dots.set(`${row},${col}`, [x, y, px[i + 1] > 128]);
    }
  }
  for (const [lon, lat, id] of world.islands || []) {
    const p = projection([lon, lat]);
    if (!p || p[0] < 0 || p[0] >= W || p[1] < 0 || p[1] >= H) continue;
    const row = Math.max(0, Math.round((p[1] - gap / 2) / rowH));
    const col = Math.max(0, Math.round((p[0] - (row % 2 ? gap : gap / 2)) / gap));
    const k = `${row},${col}`;
    if (!dots.has(k)) dots.set(k, [(row % 2 ? gap : gap / 2) + col * gap, gap / 2 + row * rowH, LIT.has(id)]);
  }
  const plain = new Path2D();
  const bright = new Path2D();
  for (const [x, y, on] of dots.values()) {
    const target = on ? bright : plain;
    target.moveTo(x + r, y);
    target.arc(x, y, r, 0, Math.PI * 2);
  }
  ctx.fillStyle = colors.dot;
  ctx.fill(plain);
  ctx.fillStyle = colors.lit;
  ctx.fill(bright);
}

/**
 * Greedy label placement: each language (in PINS order) takes its first place not under a card, then the nearest
 * free spot for its chip around the marker (above first). Chips never overlap a card, another chip or another
 * marker, and no connecting line crosses a chip or another line; a language with no room is left out (on phones,
 * the later ones).
 */
function placePins(view, W, H, projection, blocked, sizes) {
  const inside = (p, r, pad) => p[0] > r[0] - pad && p[0] < r[2] + pad && p[1] > r[1] - pad && p[1] < r[3] + pad;
  const overlaps = (a, b, pad) => a[0] < b[2] + pad && a[2] > b[0] - pad && a[1] < b[3] + pad && a[3] > b[1] - pad;
  const markers = PINS.map((pin) => pin.places.map((ll) => projection(ll))
    .find((p) => p && p[0] > 8 && p[0] < W - 8 && p[1] > 8 && p[1] < H - 8 && !blocked.some((r) => inside(p, r, 10))));
  const taken = [];
  const lines = [];
  const placed = [];
  const most = W < 560 ? 8 : PINS.length;  // a phone's small map gets the most-spoken ones only
  PINS.forEach((pin, i) => {
    const at = markers[i];
    const [w, h] = sizes[i];
    if (!at || placed.length >= most) return;
    const others = markers.filter((p, j) => p && j !== i);
    for (const box of candidates(at, w, h)) {
      if (box[0] < 6 || box[1] < 6 || box[2] > W - 6 || box[3] > H - 6) continue;
      if (blocked.some((r) => overlaps(box, r, 6)) || taken.some((r) => overlaps(box, r, 4))) continue;
      if (others.some((p) => inside(p, box, 5))) continue;
      const line = [at, nearest(at, box)];
      if (taken.some((r) => crossesBox(line, r)) || lines.some((l) => crosses(line, l))) continue;
      if (lines.some((l) => crossesBox(l, box))) continue;
      taken.push(box);
      lines.push(line);
      placed.push({ i, at, box, end: line[1] });
      return;
    }
  });

  const shown = new Set(placed.map((p) => p.i));
  view.chips.forEach((chip, i) => {
    chip.hidden = !shown.has(i);
    if (chip.hidden) chip.classList.remove("is-new");  // a hidden chip's entrance never ends
  });
  const svg = view.leaders;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.replaceChildren();
  placed.forEach(({ i, at, box, end }, n) => {
    const chip = view.chips[i];
    chip.style.left = `${box[0]}px`;
    chip.style.top = `${box[1]}px`;
    if (!view.shown) {
      chip.style.setProperty("--i", n);
      chip.classList.add("is-new");
    }
    const g = el("g", { class: "hero-pin" });
    if (Math.hypot(end[0] - at[0], end[1] - at[1]) > 4) {
      g.append(el("line", { x1: at[0], y1: at[1], x2: end[0], y2: end[1] }));
    }
    g.append(el("circle", { class: "hero-pulse", cx: at[0], cy: at[1], r: 3.5 }),
      el("circle", { class: "hero-marker", cx: at[0], cy: at[1], r: 3.5 }));
    svg.append(g);
  });
  view.shown = true;
}

// Directions to try around a marker (degrees, 0 = right, -90 = up): above first, then sideways, then below.
const DIRECTIONS = [-90, -67.5, -112.5, -45, -135, -22.5, -157.5, 0, 180, 22.5, 157.5, 45, 135, 67.5, 112.5, 90];

/** Chip boxes around a marker, nearest first (16 directions, up to about 140 px away). */
function candidates([x, y], w, h) {
  const out = [];
  for (const d of [12, 22, 34, 48, 64, 82, 102, 124, 142]) {
    for (const deg of DIRECTIONS) {
      const c = Math.cos((deg * Math.PI) / 180);
      const s = Math.sin((deg * Math.PI) / 180);
      const cx = x + c * (d + (w / 2) * Math.abs(c));
      const cy = y + s * (d + (h / 2) * Math.abs(s));
      out.push([cx - w / 2, cy - h / 2]);
    }
  }
  return out.map(([left, top]) => [left, top, left + w, top + h].map(Math.round));
}

/** The point of a box nearest to p (where a connecting line meets the chip). */
function nearest(p, box) {
  return [Math.min(Math.max(p[0], box[0]), box[2]), Math.min(Math.max(p[1], box[1]), box[3])];
}

/** Whether two segments cross (touching at an end does not count). */
function crosses([a, b], [c, d]) {
  const turn = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  return turn(a, b, c) * turn(a, b, d) < 0 && turn(c, d, a) * turn(c, d, b) < 0;
}

/** Whether a segment passes through a box (shrunk by 2 px, so a line ending on its own chip's edge is fine). */
function crossesBox(line, [x0, y0, x1, y1]) {
  const b = [x0 + 2, y0 + 2, x1 - 2, y1 - 2];
  const inBox = (p) => p[0] > b[0] && p[0] < b[2] && p[1] > b[1] && p[1] < b[3];
  if (inBox(line[0]) || inBox(line[1])) return true;
  const corners = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
  return corners.some((c, j) => crosses(line, [c, corners[(j + 1) % 4]]));
}

function el(name, attrs) {
  const node = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}
