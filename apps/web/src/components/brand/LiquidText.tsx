// Liquid Text: the wordmark rendered as a viscous surface. The word is rasterised once into a
// signed distance field; a fragment shader unions it (smooth-min) with a short sprung trail of
// metaballs that follows the pointer, so dragging through a letter pulls a bead of ink off it.
// Let go and the trail sinks back into the nearest stroke.
//
// Adapted from the owner's reference component (auth hero, D96): no animation library, the ink
// colour comes from the --color-text token and follows the theme, and it falls back to plain text
// without WebGL2 or with reduced motion.

import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type RefObject } from "react";

export interface LiquidTextProps {
  text: string;
  /** Upper bound for the font size in CSS px. The type shrinks to fit narrower containers. */
  fontSize?: number;
  fontWeight?: number;
  /** 0 = runny, 1 = thick and slow. */
  viscosity?: number;
  /** A slow drifting blob keeps the surface alive when nobody is pointing at it. */
  autoplay?: boolean;
  className?: string;
}

const MAX_TRAIL = 10;
const TRAIL = 8;
const INF = 1e20;
const px = (n: number) => `${String(n)}px`;
const N = String(MAX_TRAIL); // array size in the shader

// ─── Environment ─────────────────────────────────────────────────────────────

let webgl2Support: boolean | null = null;
function getWebGL2Support(): boolean {
  if (webgl2Support === null) {
    try {
      const ctx = document.createElement("canvas").getContext("webgl2");
      webgl2Support = !!ctx;
      ctx?.getExtension("WEBGL_lose_context")?.loseContext();
    } catch {
      webgl2Support = false;
    }
  }
  return webgl2Support;
}
const subscribeNoop = () => () => undefined;

const REDUCED = "(prefers-reduced-motion: reduce)";
const hasMatchMedia = () => typeof window.matchMedia === "function";
function subscribeReduced(cb: () => void) {
  if (!hasMatchMedia()) return () => undefined;
  const mq = window.matchMedia(REDUCED);
  mq.addEventListener("change", cb);
  return () => { mq.removeEventListener("change", cb); };
}
const getReduced = () => !hasMatchMedia() || window.matchMedia(REDUCED).matches;

// Theme changes (data-theme on <html> or the OS setting) re-read the ink token.
function subscribeTheme(cb: () => void) {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
  if (!hasMatchMedia()) return () => { mo.disconnect(); };
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", cb);
  return () => { mo.disconnect(); mq.removeEventListener("change", cb); };
}
const getInk = () => getComputedStyle(document.documentElement).getPropertyValue("--color-text").trim();

// StrictMode re-runs effects on the same canvas; the context release waits a tick so the
// second run does not get a dead context.
const pendingRelease = new WeakMap<HTMLCanvasElement, number>();
function claimCanvas(canvas: HTMLCanvasElement) {
  const t = pendingRelease.get(canvas);
  if (t !== undefined) { window.clearTimeout(t); pendingRelease.delete(canvas); }
}
function releaseCanvas(canvas: HTMLCanvasElement, gl: WebGL2RenderingContext) {
  pendingRelease.set(canvas, window.setTimeout(() => {
    pendingRelease.delete(canvas);
    if (!gl.isContextLost()) gl.getExtension("WEBGL_lose_context")?.loseContext();
  }, 0));
}

function useElementWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => { if (entry) setWidth(Math.round(entry.contentRect.width)); });
    ro.observe(el);
    return () => { ro.disconnect(); };
  }, [ref]);
  return width;
}

/** requestAnimationFrame loop that runs only while the element is on screen and the tab is visible. */
function useVisibleLoop(ref: RefObject<HTMLElement | null>, frame: (dt: number) => void, enabled: boolean) {
  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled || typeof IntersectionObserver === "undefined") return;
    let raf = 0;
    let last = 0;
    let onScreen = true;
    const tick = (t: number) => {
      const dt = last ? Math.min(0.05, (t - last) / 1000) : 1 / 60;
      last = t;
      frame(dt);
      raf = requestAnimationFrame(tick);
    };
    const sync = () => {
      const run = onScreen && document.visibilityState === "visible";
      if (run && !raf) { last = 0; raf = requestAnimationFrame(tick); }
      if (!run && raf) { cancelAnimationFrame(raf); raf = 0; }
    };
    const io = new IntersectionObserver(([entry]) => { onScreen = entry?.isIntersecting ?? true; sync(); });
    io.observe(el);
    document.addEventListener("visibilitychange", sync);
    sync();
    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", sync);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [ref, frame, enabled]);
}

// ─── Colour + layout ─────────────────────────────────────────────────────────

let scratchCtx: CanvasRenderingContext2D | null = null;
function getScratch(): CanvasRenderingContext2D | null {
  scratchCtx ??= document.createElement("canvas").getContext("2d");
  return scratchCtx;
}

function parseColor(input: string): [number, number, number] {
  const ctx = getScratch();
  if (!ctx || !input) return [0.5, 0.5, 0.5];
  ctx.fillStyle = input;
  const v = ctx.fillStyle;
  if (v.startsWith("#")) {
    const n = parseInt(v.slice(1, 7), 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }
  const m = v.match(/[\d.]+/g);
  if (!m || m.length < 3) return [0.5, 0.5, 0.5];
  return [Number(m[0]) / 255, Number(m[1]) / 255, Number(m[2]) / 255];
}

/** Perceived lightness, to pick the dark or light shading recipe. */
const isLightInk = (c: [number, number, number]) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] > 0.5;

interface Layout {
  width: number;
  height: number;
  fontSize: number;
  font: string;
  tracking: number;
  baseline: number;
  textWidth: number;
  inkTop: number;
  inkBottom: number;
}

function setTracking(ctx: CanvasRenderingContext2D, spacing: number) {
  if ("letterSpacing" in ctx) (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = px(spacing);
}

function computeLayout(width: number, text: string, family: string, weight: number, maxFont: number): Layout | null {
  const ctx = getScratch();
  if (!ctx || width < 8) return null;
  const setFont = (size: number) => { ctx.font = `${String(weight)} ${px(size)} ${family}`; setTracking(ctx, -0.025 * size); };
  setFont(100);
  const w100 = Math.max(1, ctx.measureText(text).width);
  const fontSize = Math.max(14, Math.min(maxFont, (width * 0.82 * 100) / w100));
  setFont(fontSize);
  const m = ctx.measureText(text);
  const asc = m.actualBoundingBoxAscent || fontSize * 0.72;
  const desc = m.actualBoundingBoxDescent || 0;
  const height = Math.round(fontSize * 1.6);
  const baseline = height * 0.53 + (asc - desc) / 2;
  return {
    width, height, fontSize,
    font: `${String(weight)} ${px(fontSize)} ${family}`,
    tracking: -0.025 * fontSize,
    baseline,
    textWidth: m.width,
    inkTop: baseline - asc,
    inkBottom: baseline + desc,
  };
}

function sizeCanvas(canvas: HTMLCanvasElement, w: number, h: number): number {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.width = px(w);
  canvas.style.height = px(h);
  return dpr;
}

// ─── Signed distance field (TinySDF style) ───────────────────────────────────

function edt1d(grid: Float64Array, offset: number, stride: number, length: number, f: Float64Array, v: Uint32Array, z: Float64Array) {
  v[0] = 0;
  z[0] = -INF;
  z[1] = INF;
  f[0] = grid[offset] ?? 0;
  for (let q = 1, k = 0; q < length; q++) {
    f[q] = grid[offset + q * stride] ?? 0;
    const q2 = q * q;
    let s: number;
    do {
      const r = v[k] ?? 0;
      s = ((f[q] ?? 0) - (f[r] ?? 0) + q2 - r * r) / (q - r) / 2;
    } while (s <= (z[k] ?? 0) && --k > -1);
    k++;
    v[k] = q;
    z[k] = s;
    z[k + 1] = INF;
  }
  for (let q = 0, k = 0; q < length; q++) {
    while ((z[k + 1] ?? INF) < q) k++;
    const r = v[k] ?? 0;
    const qr = q - r;
    grid[offset + q * stride] = (f[r] ?? 0) + qr * qr;
  }
}

function edt(grid: Float64Array, w: number, h: number, f: Float64Array, v: Uint32Array, z: Float64Array) {
  for (let x = 0; x < w; x++) edt1d(grid, x, w, h, f, v, z);
  for (let y = 0; y < h; y++) edt1d(grid, y * w, 1, w, f, v, z);
}

interface Field {
  data: Float32Array; // signed distance in CSS px, positive outside
  packed: Float32Array; // RG: sharp distance, softened distance (for normals)
  w: number;
  h: number;
  scale: number; // texels per CSS px
}

function boxBlur(src: Float32Array, dst: Float32Array, len: number, lines: number, r: number, step: number, stride: number) {
  const span = 2 * r + 1;
  for (let line = 0; line < lines; line++) {
    const base = line * stride;
    let acc = 0;
    for (let k = -r; k <= r; k++) acc += src[base + Math.min(len - 1, Math.max(0, k)) * step] ?? 0;
    for (let i = 0; i < len; i++) {
      dst[base + i * step] = acc / span;
      const out = Math.max(0, i - r);
      const inn = Math.min(len - 1, i + r + 1);
      acc += (src[base + inn * step] ?? 0) - (src[base + out * step] ?? 0);
    }
  }
}

function buildField(layout: Layout, text: string): Field | null {
  const scale = Math.min(1.25, 1800 / layout.width);
  const w = Math.max(2, Math.round(layout.width * scale));
  const h = Math.max(2, Math.round(layout.height * scale));
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.scale(scale, scale);
  ctx.font = layout.font;
  setTracking(ctx, layout.tracking);
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "white";
  ctx.fillText(text, layout.width / 2, layout.baseline);
  const img = ctx.getImageData(0, 0, w, h).data;

  const n = w * h;
  const outer = new Float64Array(n);
  const inner = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const a = (img[i * 4 + 3] ?? 0) / 255;
    if (a >= 1) { outer[i] = 0; inner[i] = INF; }
    else if (a <= 0) { outer[i] = INF; inner[i] = 0; }
    else {
      const d = 0.5 - a;
      outer[i] = d > 0 ? d * d : 0;
      inner[i] = d < 0 ? d * d : 0;
    }
  }
  const len = Math.max(w, h);
  const f = new Float64Array(len);
  const v = new Uint32Array(len);
  const z = new Float64Array(len + 1);
  edt(outer, w, h, f, v, z);
  edt(inner, w, h, f, v, z);
  const data = new Float32Array(n);
  for (let i = 0; i < n; i++) data[i] = (Math.sqrt(outer[i] ?? 0) - Math.sqrt(inner[i] ?? 0)) / scale;
  // A softened copy rounds off the medial-axis ridges so the surface shades like a bead.
  const soft = Float32Array.from(data);
  const tmp = new Float32Array(n);
  const radius = Math.max(1, Math.round(layout.fontSize * 0.035 * scale));
  for (let pass = 0; pass < 3; pass++) {
    boxBlur(soft, tmp, w, h, radius, 1, w);
    boxBlur(tmp, soft, h, w, radius, w, 1);
  }
  const packed = new Float32Array(n * 2);
  for (let i = 0; i < n; i++) {
    packed[i * 2] = data[i] ?? 0;
    packed[i * 2 + 1] = soft[i] ?? 0;
  }
  return { data, packed, w, h, scale };
}

function sampleField(field: Field, x: number, y: number): number {
  const fx = Math.min(field.w - 1, Math.max(0, Math.round(x * field.scale)));
  const fy = Math.min(field.h - 1, Math.max(0, Math.round(y * field.scale)));
  return field.data[fy * field.w + fx] ?? INF;
}

/** Walks a point onto the letter surface (slightly inside) along the field gradient. */
function nearestInside(field: Field, x: number, y: number, inset: number): [number, number] {
  let px = x;
  let py = y;
  for (let i = 0; i < 10; i++) {
    const d = sampleField(field, px, py) + inset;
    if (Math.abs(d) < 0.5) break;
    const e = 1.5;
    const gx = (sampleField(field, px + e, py) - sampleField(field, px - e, py)) / (2 * e);
    const gy = (sampleField(field, px, py + e) - sampleField(field, px, py - e)) / (2 * e);
    const gl = Math.hypot(gx, gy) || 1;
    px -= (gx / gl) * d;
    py -= (gy / gl) * d;
  }
  return [px, py];
}

// ─── Shaders ─────────────────────────────────────────────────────────────────

const VERT = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

const FRAG = `#version 300 es
precision highp float;
uniform sampler2D uSdf;
uniform vec2 uSize;
uniform float uDpr;
uniform float uCanvasH;
uniform vec4 uBlob[${N}];
uniform vec2 uWarp[${N}];
uniform int uCount;
uniform float uSigma;
uniform float uBevel;
uniform vec3 uInk;
uniform float uSpec;
uniform float uShade;
out vec4 outColor;

float smin(float a, float b, float k) {
  float h = max(k - abs(a - b), 0.0) / k;
  return min(a, b) - h * h * k * 0.25;
}

float glyph(vec2 p, float soft) {
  vec2 t = texture(uSdf, p / uSize).rg;
  return mix(t.r, t.g, soft);
}

float field(vec2 p, float soft) {
  vec2 warp = vec2(0.0);
  float wsum = 0.0;
  for (int i = 0; i < ${N}; i++) {
    if (i >= uCount) break;
    vec2 d = p - uBlob[i].xy;
    float g = exp(-dot(d, d) / (uSigma * uSigma));
    warp += uWarp[i] * g;
    wsum += g;
  }
  warp /= max(1.0, wsum);
  float f = glyph(p - warp, soft);
  for (int i = 0; i < ${N}; i++) {
    if (i >= uCount) break;
    float r = uBlob[i].z;
    if (r < 0.05) continue;
    float b = length(p - uBlob[i].xy) - r;
    f = smin(f, b, r * 1.45);
  }
  return f;
}

void main() {
  vec2 p = vec2(gl_FragCoord.x, uCanvasH - gl_FragCoord.y) / uDpr;
  float f = field(p, 0.0);
  float fw = max(fwidth(f), 1e-4);
  float alpha = clamp(0.5 - f / fw, 0.0, 1.0);
  if (alpha <= 0.0) { outColor = vec4(0.0); return; }

  float e = 1.0;
  vec2 grad = vec2(
    field(p + vec2(e, 0.0), 1.0) - field(p - vec2(e, 0.0), 1.0),
    field(p + vec2(0.0, e), 1.0) - field(p - vec2(0.0, e), 1.0)
  ) / (2.0 * e);
  float fs = field(p, 1.0);
  float gl = length(grad);
  vec2 n2 = gl > 1e-4 ? grad / gl : vec2(0.0);

  // Circular cross-section: steep at the rim, flat in the middle of thick strokes.
  float s = 1.0 - clamp(-min(fs, f + 0.5) / uBevel, 0.0, 1.0);
  s = pow(s, 1.6);
  vec3 N = normalize(vec3(n2 * s, sqrt(max(0.0, 1.0 - s * s))));
  vec3 L = normalize(vec3(-0.45, -0.7, 0.62));
  float diff = clamp(dot(N, L), 0.0, 1.0);
  vec3 H = normalize(L + vec3(0.0, 0.0, 1.0));
  float spec = pow(max(dot(N, H), 0.0), 48.0);

  vec3 col = uInk * mix(1.0 - uShade, 1.0, diff);
  col += vec3(spec * uSpec);
  outColor = vec4(col * alpha, alpha);
}`;

function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader | null {
  const sh = gl.createShader(type);
  if (!sh) return null;
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS) && !gl.isContextLost()) {
    gl.deleteShader(sh);
    return null;
  }
  return sh;
}

// ─── Simulation ──────────────────────────────────────────────────────────────

interface Sim {
  x: Float32Array;
  y: Float32Array;
  vx: Float32Array;
  vy: Float32Array;
  mass: number;
  massV: number;
  load: number;
  mode: "idle" | "pointer" | "release";
  tx: number;
  ty: number;
  homeX: number;
  homeY: number;
  releaseT: number;
  idleBlend: number;
  clock: number;
  seeded: boolean;
  anchorX: number;
  anchorY: number;
  tether: number;
}

function createSim(): Sim {
  return {
    x: new Float32Array(MAX_TRAIL), y: new Float32Array(MAX_TRAIL),
    vx: new Float32Array(MAX_TRAIL), vy: new Float32Array(MAX_TRAIL),
    mass: 0, massV: 0, load: 0.5, mode: "idle", tx: 0, ty: 0, homeX: 0, homeY: 0,
    releaseT: 0, idleBlend: 1, clock: 0, seeded: false, anchorX: 0, anchorY: 0, tether: 0,
  };
}

function idlePoint(layout: Layout, t: number): [number, number] {
  const capH = layout.inkBottom - layout.inkTop;
  // Rides the top line of the word, dipping into the letters and lifting beads off them.
  const y = layout.inkTop + capH * (0.04 + 0.2 * Math.sin(t * 0.53 + 1.1) + 0.08 * Math.sin(t * 1.27));
  return [layout.width / 2 + layout.textWidth * 0.44 * Math.sin(t * 0.21), y];
}

function stepSim(sim: Sim, dt: number, layout: Layout, field: Field, visc: number, autoplay: boolean) {
  const n = TRAIL;
  if (!sim.seeded) {
    const [ix, iy] = idlePoint(layout, sim.clock);
    sim.x.fill(ix);
    sim.y.fill(iy);
    sim.seeded = true;
  }

  let massTarget = 0;
  let gx = sim.tx;
  let gy = sim.ty;
  if (sim.mode === "pointer") massTarget = 1;
  else if (sim.mode === "release") {
    sim.releaseT += dt;
    gx = sim.homeX;
    gy = sim.homeY;
    if (sim.releaseT > 2.2 && autoplay) { sim.mode = "idle"; sim.idleBlend = 0; }
  }
  if (sim.mode === "idle") {
    if (!autoplay) { gx = sim.homeX; gy = sim.homeY; }
    else {
      sim.clock += dt;
      sim.idleBlend = Math.min(1, sim.idleBlend + dt / 2.4);
      const b = sim.idleBlend * sim.idleBlend * (3 - 2 * sim.idleBlend);
      const [ix, iy] = idlePoint(layout, sim.clock);
      gx = sim.homeX + (ix - sim.homeX) * b;
      gy = sim.homeY + (iy - sim.homeY) * b;
      massTarget = 0.55 * b;
    }
  }

  const k = 330 - 270 * visc;
  const c = 2 * 0.62 * Math.sqrt(k);
  const kf = k * 1.25;
  const cf = 2 * 0.48 * Math.sqrt(kf);
  const km = 70;
  const cm = 2 * 0.3 * Math.sqrt(km);

  // Surface tension: a head that leaves a stroke stays tethered to it until the neck snaps.
  const headX = sim.x[0] ?? 0;
  const headY = sim.y[0] ?? 0;
  if (sim.mode === "pointer" || (sim.mode === "idle" && autoplay)) {
    if (sampleField(field, headX, headY) < 0) {
      sim.tether = Math.min(1, sim.tether + dt * 8);
      [sim.anchorX, sim.anchorY] = nearestInside(field, headX, headY, layout.fontSize * 0.04);
    } else if (sim.tether > 0) {
      const stretch = Math.hypot(headX - sim.anchorX, headY - sim.anchorY);
      if (stretch > layout.fontSize * (0.42 + 0.4 * visc)) sim.tether = 0;
    }
  } else {
    sim.tether = Math.max(0, sim.tether - dt * 3);
  }

  const steps = Math.max(1, Math.ceil(dt / (1 / 120)));
  const h = dt / steps;
  for (let s = 0; s < steps; s++) {
    for (let i = 0; i < n; i++) {
      const tx = i === 0 ? gx : (sim.x[i - 1] ?? 0);
      const ty = i === 0 ? gy : (sim.y[i - 1] ?? 0);
      const kk = i === 0 ? k : kf;
      const cc = i === 0 ? c : cf;
      const xi = sim.x[i] ?? 0;
      const yi = sim.y[i] ?? 0;
      let fx = (tx - xi) * kk;
      let fy = (ty - yi) * kk;
      if (i > 0 && sim.tether > 0) {
        const w = sim.tether * Math.pow(i / (n - 1), 1.3) * 1.6;
        fx += (sim.anchorX - xi) * kk * w;
        fy += (sim.anchorY - yi) * kk * w;
      }
      const vx = (sim.vx[i] ?? 0) + (fx - (sim.vx[i] ?? 0) * cc) * h;
      const vy = (sim.vy[i] ?? 0) + (fy - (sim.vy[i] ?? 0) * cc) * h;
      sim.vx[i] = vx;
      sim.vy[i] = vy;
      sim.x[i] = xi + vx * h;
      sim.y[i] = yi + vy * h;
    }
    sim.massV += ((massTarget - sim.mass) * km - sim.massV * cm) * h;
    sim.mass += sim.massV * h;
  }

  // Dragging through a letter loads the blob with ink; open air slowly thins it.
  const inside = sampleField(field, sim.x[0] ?? 0, sim.y[0] ?? 0) < layout.fontSize * 0.02;
  sim.load = inside ? Math.min(1, sim.load + dt * 5) : Math.max(0.4, sim.load - dt * 0.35);
}

// ─── Component ───────────────────────────────────────────────────────────────

interface GLState {
  gl: WebGL2RenderingContext;
  prog: WebGLProgram;
  tex: WebGLTexture;
  u: Record<string, WebGLUniformLocation | null>;
}

const UNIFORMS = ["uSdf", "uSize", "uDpr", "uCanvasH", "uBlob", "uWarp", "uCount", "uSigma", "uBevel", "uInk", "uSpec", "uShade"];

export function LiquidText({ text, fontSize = 200, fontWeight = 700, viscosity = 0.55, autoplay = true, className = "" }: LiquidTextProps) {
  const supported = useSyncExternalStore(subscribeNoop, getWebGL2Support, () => false);
  const reduced = useSyncExternalStore(subscribeReduced, getReduced, () => true);
  const ink = useSyncExternalStore(subscribeTheme, getInk, () => "");
  const animated = supported && !reduced;

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const width = useElementWidth(wrapRef);
  const [size, setSize] = useState<{ height: number; fontSize: number } | null>(null);
  const [epoch, setEpoch] = useState(0);

  const glRef = useRef<GLState | null>(null);
  const fieldRef = useRef<Field | null>(null);
  const layoutRef = useRef<Layout | null>(null);
  const dprRef = useRef(1);
  const simRef = useRef<Sim>(createSim());
  const inkRef = useRef<[number, number, number]>([0.5, 0.5, 0.5]);
  const blobBuf = useRef(new Float32Array(MAX_TRAIL * 4));
  const warpBuf = useRef(new Float32Array(MAX_TRAIL * 2));

  const draw = useCallback(() => {
    const g = glRef.current;
    const lay = layoutRef.current;
    const canvas = canvasRef.current;
    if (!g || !lay || !canvas || g.gl.isContextLost()) return;
    const { gl, u } = g;
    const sim = simRef.current;
    const R = lay.fontSize * 0.13;
    const visc = viscosity;
    const blob = blobBuf.current;
    const warp = warpBuf.current;
    const maxWarp = lay.fontSize * 0.05;
    const warpTime = 0.028 - visc * 0.01;
    const mass = Math.max(0, sim.mass);
    for (let i = 0; i < MAX_TRAIL; i++) {
      const taper = i === 0 ? 1 : 0.62 - 0.34 * (1 - 0.6 * sim.tether) * ((i - 1) / Math.max(1, TRAIL - 2));
      blob[i * 4] = sim.x[i] ?? 0;
      blob[i * 4 + 1] = sim.y[i] ?? 0;
      blob[i * 4 + 2] = i < TRAIL ? R * mass * (0.45 + 0.55 * sim.load) * taper : 0;
      blob[i * 4 + 3] = 0;
      let wx = (sim.vx[i] ?? 0) * warpTime * Math.min(1, mass * 1.4);
      let wy = (sim.vy[i] ?? 0) * warpTime * Math.min(1, mass * 1.4);
      const wl = Math.hypot(wx, wy);
      if (wl > maxWarp) { wx *= maxWarp / wl; wy *= maxWarp / wl; }
      warp[i * 2] = wx;
      warp[i * 2 + 1] = wy;
    }
    const inkRgb = inkRef.current;
    const light = isLightInk(inkRgb);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(g.prog);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, g.tex);
    gl.uniform1i(u.uSdf ?? null, 0);
    gl.uniform2f(u.uSize ?? null, lay.width, lay.height);
    gl.uniform1f(u.uDpr ?? null, dprRef.current);
    gl.uniform1f(u.uCanvasH ?? null, canvas.height);
    gl.uniform4fv(u.uBlob ?? null, blob);
    gl.uniform2fv(u.uWarp ?? null, warp);
    gl.uniform1i(u.uCount ?? null, TRAIL);
    gl.uniform1f(u.uSigma ?? null, R * 1.8);
    gl.uniform1f(u.uBevel ?? null, Math.max(2, lay.fontSize * 0.085));
    gl.uniform3f(u.uInk ?? null, inkRgb[0], inkRgb[1], inkRgb[2]);
    gl.uniform1f(u.uSpec ?? null, light ? 0.55 : 0.75);
    gl.uniform1f(u.uShade ?? null, light ? 0.32 : 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }, [viscosity]);

  // Ink follows the theme token.
  useEffect(() => {
    inkRef.current = parseColor(ink);
    draw();
  }, [ink, draw]);

  // GL setup / teardown. `epoch` bumps after a context restore.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !supported) return;
    claimCanvas(canvas);
    const gl = canvas.getContext("webgl2", { premultipliedAlpha: true, antialias: false, alpha: true });
    if (!gl) return;
    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    const prog = gl.createProgram();
    const buf = gl.createBuffer();
    const tex = gl.createTexture();
    if (!vs || !fs) return;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.bindAttribLocation(prog, 0, "aPos");
    gl.linkProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const u: GLState["u"] = {};
    for (const name of UNIFORMS) u[name] = gl.getUniformLocation(prog, name);
    glRef.current = { gl, prog, tex, u };

    const onLost = (e: Event) => { e.preventDefault(); glRef.current = null; };
    const onRestored = () => { setEpoch((v) => v + 1); };
    canvas.addEventListener("webglcontextlost", onLost);
    canvas.addEventListener("webglcontextrestored", onRestored);
    return () => {
      canvas.removeEventListener("webglcontextlost", onLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
      glRef.current = null;
      if (!gl.isContextLost()) {
        gl.deleteTexture(tex);
        gl.deleteBuffer(buf);
        gl.deleteProgram(prog);
        gl.deleteShader(vs);
        gl.deleteShader(fs);
        releaseCanvas(canvas, gl);
      }
    };
  }, [supported, epoch]);

  // Layout, canvas size and the distance field. Re-runs on resize or text change.
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || width < 8) return;
    let cancelled = false;
    const family = getComputedStyle(wrap).fontFamily || "sans-serif";
    const run = () => {
      if (cancelled) return;
      const lay = computeLayout(width, text, family, fontWeight, fontSize);
      if (!lay) return;
      setSize((prev) => (prev?.height === lay.height && prev.fontSize === lay.fontSize ? prev : { height: lay.height, fontSize: lay.fontSize }));
      layoutRef.current = lay;
      if (!canvas || !supported) return;
      const field = buildField(lay, text);
      if (!field) return;
      fieldRef.current = field;
      dprRef.current = sizeCanvas(canvas, lay.width, lay.height);
      const g = glRef.current;
      if (g && !g.gl.isContextLost()) {
        g.gl.bindTexture(g.gl.TEXTURE_2D, g.tex);
        g.gl.pixelStorei(g.gl.UNPACK_ALIGNMENT, 1);
        g.gl.texImage2D(g.gl.TEXTURE_2D, 0, g.gl.RG16F, field.w, field.h, 0, g.gl.RG, g.gl.FLOAT, field.packed);
      }
      // Park the trail on the text so the first frame never flies in from the corner.
      const sim = simRef.current;
      [sim.homeX, sim.homeY] = nearestInside(field, lay.width / 2, (lay.inkTop + lay.inkBottom) / 2, lay.fontSize * 0.03);
      if (reduced) { sim.mass = 0; sim.massV = 0; }
      draw();
    };
    // The exact weight must be loaded before rasterising.
    document.fonts.load(`${String(fontWeight)} 100px ${family}`, text).then(run, run);
    return () => { cancelled = true; };
  }, [width, text, fontWeight, fontSize, supported, reduced, epoch, draw]);

  // Pointer input.
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || !animated) return;
    const toLocal = (e: PointerEvent): [number, number] | null => {
      const lay = layoutRef.current;
      if (!lay) return null;
      const rect = wrap.getBoundingClientRect();
      const sx = rect.width > 0 ? lay.width / rect.width : 1;
      const sy = rect.height > 0 ? lay.height / rect.height : 1;
      return [(e.clientX - rect.left) * sx, (e.clientY - rect.top) * sy];
    };
    const onMove = (e: PointerEvent) => {
      const pt = toLocal(e);
      const lay = layoutRef.current;
      if (!pt || !lay) return;
      const sim = simRef.current;
      sim.mode = "pointer";
      const m = lay.fontSize * 0.1;
      sim.tx = Math.min(lay.width - m, Math.max(m, pt[0]));
      sim.ty = Math.min(lay.height - m, Math.max(m, pt[1]));
    };
    const onLeave = () => {
      const sim = simRef.current;
      const field = fieldRef.current;
      const lay = layoutRef.current;
      if (sim.mode !== "pointer" || !field || !lay) return;
      [sim.homeX, sim.homeY] = nearestInside(field, sim.x[0] ?? 0, sim.y[0] ?? 0, lay.fontSize * 0.03);
      sim.mode = "release";
      sim.releaseT = 0;
    };
    const onDown = (e: PointerEvent) => {
      if (e.button === 0) {
        try { wrap.setPointerCapture(e.pointerId); } catch { /* capture is best-effort */ }
      }
      onMove(e);
    };
    const onUp = (e: PointerEvent) => {
      if (wrap.hasPointerCapture(e.pointerId)) wrap.releasePointerCapture(e.pointerId);
      const rect = wrap.getBoundingClientRect();
      const outside = e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom;
      if (e.pointerType !== "mouse" || outside) onLeave();
    };
    wrap.addEventListener("pointermove", onMove);
    wrap.addEventListener("pointerdown", onDown);
    wrap.addEventListener("pointerleave", onLeave);
    wrap.addEventListener("pointercancel", onLeave);
    wrap.addEventListener("pointerup", onUp);
    return () => {
      wrap.removeEventListener("pointermove", onMove);
      wrap.removeEventListener("pointerdown", onDown);
      wrap.removeEventListener("pointerleave", onLeave);
      wrap.removeEventListener("pointercancel", onLeave);
      wrap.removeEventListener("pointerup", onUp);
    };
  }, [animated]);

  const frame = useCallback((dt: number) => {
    const lay = layoutRef.current;
    const field = fieldRef.current;
    if (!lay || !field || !glRef.current) return;
    stepSim(simRef.current, dt, lay, field, viscosity, autoplay);
    draw();
  }, [draw, viscosity, autoplay]);
  useVisibleLoop(wrapRef, frame, animated);

  return (
    <div
      ref={wrapRef}
      role="img"
      aria-label={text}
      className={`relative w-full touch-pan-y select-none font-display ${className}`}
      style={{ height: size?.height, minHeight: size ? undefined : "1.6em", fontWeight }}
    >
      {supported ? (
        <canvas ref={canvasRef} aria-hidden className="absolute left-0 top-0 block" />
      ) : (
        <span
          aria-hidden
          className="absolute inset-0 flex items-center justify-center whitespace-nowrap leading-none tracking-tight text-text"
          style={{ fontSize: size?.fontSize ?? "clamp(48px, 10vw, 160px)" }}
        >
          {text}
        </span>
      )}
    </div>
  );
}
