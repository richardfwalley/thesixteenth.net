'use strict';

const canvas = document.getElementById('bg');
const ctx = canvas.getContext('2d');

let W = 0, H = 0;

function rand(min, max) { return Math.random() * (max - min) + min; }

// Draw a four-pointed star as in the Très Riches Heures manuscript
function fourPointedStar(x, y, outer, inner) {
  ctx.beginPath();
  for (let i = 0; i < 4; i++) {
    const oa = (i / 4) * Math.PI * 2 - Math.PI / 2;
    const ia = oa + Math.PI / 4;
    const ox = x + Math.cos(oa) * outer;
    const oy = y + Math.sin(oa) * outer;
    const ix = x + Math.cos(ia) * inner;
    const iy = y + Math.sin(ia) * inner;
    if (i === 0) ctx.moveTo(ox, oy);
    else ctx.lineTo(ox, oy);
    ctx.lineTo(ix, iy);
  }
  ctx.closePath();
}

// Small dot stars — the dense field of tiny gold points.
// Base positions are normalized (resize-safe); radius/angle around the pole
// are derived from them once the album's position is known.
const dotStars = Array.from({ length: 160 }, () => ({
  nx: rand(0, 1), ny: rand(0, 1),
  r: rand(0.4, 1.8),
  phase: rand(0, Math.PI * 2),
  tspeed: rand(0.0004, 0.0016),
  base: rand(0.35, 0.9),
}));

// Four-pointed gold stars — the manuscript's distinctive ✦ shapes
const fourStars = Array.from({ length: 60 }, () => ({
  nx: rand(0, 1), ny: rand(0, 1),
  outer: rand(2.5, 6.5),
  phase: rand(0, Math.PI * 2),
  tspeed: rand(0.0003, 0.0012),
  base: rand(0.3, 0.85),
}));

// — Pleiades — a named, recognisable cluster that circles the album cover
// like circumpolar stars wheeling around a pole star, starting at the top of the screen,
// brighter than the ambient field around it.
const pleiadesLocal = [
  { name: 'Alcyone',  dx: 0,   dy: 0,   mag: 'bright' },
  { name: 'Atlas',    dx: 12,  dy: -17, mag: 'mid' },
  { name: 'Electra',  dx: -27, dy: 6,   mag: 'mid' },
  { name: 'Maia',     dx: -16, dy: 4,   mag: 'mid' },
  { name: 'Merope',   dx: -9,  dy: 21,  mag: 'mid' },
  { name: 'Taygeta',  dx: -19, dy: 9,   mag: 'mid' },
  { name: 'Pleione',  dx: 10,  dy: -14, mag: 'mid' },
  { name: 'Celaeno',  dx: -23, dy: 10,  mag: 'dim' },
  { name: 'Asterope', dx: -14, dy: 16,  mag: 'dim' },
];

const PLEIADES_SCALE = 4.6;        // px per arcmin of real separation — ~16% smaller
const PLEIADES_PERIOD = 560;       // seconds per full orbit — 50% slower
const PLEIADES_TOP_MARGIN = 70;    // px clearance kept from the very top of the viewport
const PLEIADES_CLEARANCE_GAP = 26; // guaranteed px gap between the cluster and the album's edge

const SKY_PERIOD = PLEIADES_PERIOD; // ambient sky shares roughly the same speed
const DOT_SPEED_MULT = 0.85;        // background layer — a touch slower (parallax)
const FOUR_SPEED_MULT = 1.15;       // foreground layer — a touch faster (parallax)

const coverEl = document.querySelector('.cover');
const pole = { x: 0, y: 0 };
let pleiadesGeom = [];

// Computes the pole (album centre) and every star's fixed radius + starting angle
// around it — including a guaranteed floor so no Pleiades star can ever be eclipsed
// by the album, regardless of viewport size.
function computeSkyGeometry() {
  if (!coverEl) return;
  const rect = coverEl.getBoundingClientRect();
  if (rect.height === 0) return; // image box not laid out yet — wait for it to load

  pole.x = rect.left + rect.width / 2;
  pole.y = rect.top + rect.height / 2;

  const halfDiagonal = Math.hypot(rect.width, rect.height) / 2;
  const maxDy = Math.max(...pleiadesLocal.map((s) => s.dy));
  const clearanceRadius = halfDiagonal + PLEIADES_CLEARANCE_GAP + maxDy * PLEIADES_SCALE;
  const topRadius = Math.max(pole.y - PLEIADES_TOP_MARGIN, 60);
  const startRadius = Math.max(topRadius, clearanceRadius);

  pleiadesGeom = pleiadesLocal.map((s) => {
    const baseX = s.dx * PLEIADES_SCALE;
    const baseY = s.dy * PLEIADES_SCALE - startRadius;
    return {
      mag: s.mag,
      seed: s.dx * 13 + s.dy * 7,
      radius: Math.hypot(baseX, baseY),
      angle0: Math.atan2(baseY, baseX),
    };
  });

  // Ambient starfield — convert each star's base position into a radius + angle
  // around the same pole, so the whole sky can wheel slowly around the album too.
  for (const s of dotStars) {
    const x = s.nx * W, y = s.ny * H;
    s.radius = Math.hypot(x - pole.x, y - pole.y);
    s.angle0 = Math.atan2(y - pole.y, x - pole.x);
  }
  for (const s of fourStars) {
    const x = s.nx * W, y = s.ny * H;
    s.radius = Math.hypot(x - pole.x, y - pole.y);
    s.angle0 = Math.atan2(y - pole.y, x - pole.x);
  }
}

function resize() {
  W = canvas.width = window.innerWidth;
  H = canvas.height = window.innerHeight;
  computeSkyGeometry();
}
resize();
window.addEventListener('resize', resize);

if (coverEl && coverEl.complete) computeSkyGeometry();
if (coverEl) coverEl.addEventListener('load', computeSkyGeometry);

const PLEIADES_SIZES = {
  bright: { r: 3.1, glow: 15 },
  mid:    { r: 1.9, glow: 9.5 },
  dim:    { r: 1.3, glow: 6.5 },
};

function drawPleiades(t) {
  if (pleiadesGeom.length === 0) return;
  const orbitAngle = (t / PLEIADES_PERIOD) * Math.PI * 2;

  for (const s of pleiadesGeom) {
    const angle = s.angle0 + orbitAngle;
    const x = pole.x + Math.cos(angle) * s.radius;
    const y = pole.y + Math.sin(angle) * s.radius;
    const size = PLEIADES_SIZES[s.mag];
    const alpha = 0.82 + 0.18 * Math.sin(t * 0.7 + s.seed);

    const glow = ctx.createRadialGradient(x, y, 0, x, y, size.glow);
    glow.addColorStop(0,    `rgba(255, 246, 210, ${alpha * 0.9})`);
    glow.addColorStop(0.35, `rgba(247, 222, 150, ${alpha * 0.45})`);
    glow.addColorStop(1,    'rgba(247, 222, 150, 0)');
    ctx.beginPath();
    ctx.arc(x, y, size.glow, 0, Math.PI * 2);
    ctx.fillStyle = glow;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(x, y, size.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 252, 232, ${Math.min(alpha * 1.1, 1)})`;
    ctx.fill();
  }
}

let startTime = null;

function tick(now) {
  if (!startTime) startTime = now;
  const t = (now - startTime) * 0.001;

  // Deep ultramarine gradient — matching the lapis lazuli blue of the album cover
  const bg = ctx.createRadialGradient(W * 0.5, H * 0.55, 0, W * 0.5, H * 0.5, Math.max(W, H) * 0.9);
  bg.addColorStop(0,    '#0f1e7a');
  bg.addColorStop(0.5,  '#0a1450');
  bg.addColorStop(1,    '#050b28');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // — Dot stars —
  const dotAngle = (t / SKY_PERIOD) * Math.PI * 2 * DOT_SPEED_MULT;
  for (const s of dotStars) {
    let x, y;
    if (s.radius !== undefined) {
      const angle = s.angle0 + dotAngle;
      x = pole.x + Math.cos(angle) * s.radius;
      y = pole.y + Math.sin(angle) * s.radius;
    } else {
      x = s.nx * W;
      y = s.ny * H;
    }

    const alpha = s.base * (0.55 + 0.45 * Math.sin(t * s.tspeed * 1000 + s.phase));

    const glow = ctx.createRadialGradient(x, y, 0, x, y, s.r * 4.5);
    glow.addColorStop(0,   `rgba(245, 225, 140, ${alpha})`);
    glow.addColorStop(0.3, `rgba(201, 165, 90,  ${alpha * 0.35})`);
    glow.addColorStop(1,   'rgba(201, 165, 90, 0)');

    ctx.beginPath();
    ctx.arc(x, y, s.r * 4.5, 0, Math.PI * 2);
    ctx.fillStyle = glow;
    ctx.fill();

    ctx.beginPath();
    ctx.arc(x, y, s.r * 0.55, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255, 248, 210, ${Math.min(alpha * 1.4, 1)})`;
    ctx.fill();
  }

  // — Four-pointed stars —
  const fourAngle = (t / SKY_PERIOD) * Math.PI * 2 * FOUR_SPEED_MULT;
  for (const s of fourStars) {
    let x, y;
    if (s.radius !== undefined) {
      const angle = s.angle0 + fourAngle;
      x = pole.x + Math.cos(angle) * s.radius;
      y = pole.y + Math.sin(angle) * s.radius;
    } else {
      x = s.nx * W;
      y = s.ny * H;
    }

    const alpha = s.base * (0.55 + 0.45 * Math.sin(t * s.tspeed * 1000 + s.phase));
    const inner = s.outer * 0.22;

    // Soft glow
    const glow = ctx.createRadialGradient(x, y, 0, x, y, s.outer * 3.5);
    glow.addColorStop(0,   `rgba(220, 185, 90, ${alpha * 0.65})`);
    glow.addColorStop(0.45,`rgba(201, 165, 90, ${alpha * 0.2})`);
    glow.addColorStop(1,   'rgba(201, 165, 90, 0)');
    ctx.beginPath();
    ctx.arc(x, y, s.outer * 3.5, 0, Math.PI * 2);
    ctx.fillStyle = glow;
    ctx.fill();

    // Star shape
    ctx.save();
    ctx.globalAlpha = alpha;
    fourPointedStar(x, y, s.outer, inner);
    ctx.fillStyle = '#edd888';
    ctx.fill();
    ctx.restore();
  }

  // — Pleiades —
  drawPleiades(t);

  requestAnimationFrame(tick);
}

requestAnimationFrame(tick);
