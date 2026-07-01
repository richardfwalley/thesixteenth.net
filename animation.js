'use strict';

const canvas = document.getElementById('bg');
const ctx = canvas.getContext('2d');

let W = 0, H = 0;

function resize() {
  W = canvas.width = window.innerWidth;
  H = canvas.height = window.innerHeight;
}
resize();
window.addEventListener('resize', resize);

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

// Small dot stars — the dense field of tiny gold points
const dotStars = Array.from({ length: 160 }, () => ({
  x: rand(0, 1), y: rand(0, 1),
  r: rand(0.4, 1.8),
  phase: rand(0, Math.PI * 2),
  speed: rand(0.0004, 0.0016),
  base: rand(0.35, 0.9),
  dx: rand(-0.000012, 0.000012),
  dy: rand(-0.000009, 0.000009),
}));

// Four-pointed gold stars — the manuscript's distinctive ✦ shapes
const fourStars = Array.from({ length: 60 }, () => ({
  x: rand(0, 1), y: rand(0, 1),
  outer: rand(2.5, 6.5),
  phase: rand(0, Math.PI * 2),
  speed: rand(0.0003, 0.0012),
  base: rand(0.3, 0.85),
  dx: rand(-0.000010, 0.000010),
  dy: rand(-0.000008, 0.000008),
}));

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
  for (const s of dotStars) {
    s.x = (s.x + s.dx + 1.04) % 1.04;
    s.y = (s.y + s.dy + 1.04) % 1.04;

    const alpha = s.base * (0.55 + 0.45 * Math.sin(t * s.speed * 1000 + s.phase));
    const x = s.x * W, y = s.y * H;

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
  for (const s of fourStars) {
    s.x = (s.x + s.dx + 1.04) % 1.04;
    s.y = (s.y + s.dy + 1.04) % 1.04;

    const alpha = s.base * (0.55 + 0.45 * Math.sin(t * s.speed * 1000 + s.phase));
    const x = s.x * W, y = s.y * H;
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

  requestAnimationFrame(tick);
}

requestAnimationFrame(tick);
