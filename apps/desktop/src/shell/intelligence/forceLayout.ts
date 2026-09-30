/**
 * A force-directed graph layout in ~40 lines, so the Second brain can look like an Obsidian-style
 * graph without a layout dependency (d3-force is ~30 kB for the part that would get used, and this
 * app ships every dependency — no CDN).
 *
 * Ported and trimmed from the CV Naturals project's `apps/web/src/lib/forceLayout.ts` (same
 * author; lawful reuse). That version also animates a re-settle while a node is dragged; Alpha's
 * Second brain has no drag-to-reposition, so the per-frame `tick`/focus-repulsion machinery is
 * dropped and only the one-shot `settle` used for the initial layout remains.
 *
 * ponytail: no drag-to-reposition, so this only ever settles once and never animates — which is
 * also why there is nothing here that needs a prefers-reduced-motion check. Add `tick` back
 * (see CV Naturals' forceLayout.ts) if per-node dragging is wanted later.
 */

export interface SimNode {
  key: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export interface SimEdge {
  from: string;
  to: string;
}

const LINK_DISTANCE = 90;
const LINK_STRENGTH = 0.05;
const REPULSION = 9000;
const CENTER_PULL = 0.012;
const DAMPING = 0.82;
const MIN_DISTANCE = 12;

/** Constants tuned for a dozen nodes produce a hairball at two hundred; spacing scales with the
 * square root of node count so the settled graph stays at roughly constant density. */
export function spacingFor(nodeCount: number): number {
  return Math.max(1, Math.sqrt(nodeCount / 12));
}

/** The shell the graph is held inside: an egg, taller than it is wide and narrower at the top —
 * Alpha's own image for this page rather than a generic disc. The outline carries no information
 * on purpose; all the meaning is in the nodes and edges. */
export const EGG_ASPECT = 1.32;
const EGG_TAPER = 0.3;

export function eggHalfWidth(ny: number, semiWidth: number): number {
  const clamped = Math.max(-1, Math.min(1, ny));
  return semiWidth * Math.sqrt(Math.max(0, 1 - clamped * clamped)) * (1 - EGG_TAPER * clamped);
}

export function eggRadii(nodeCount: number): { semiWidth: number; semiHeight: number } {
  const semiWidth = 260 * spacingFor(nodeCount);
  return { semiWidth, semiHeight: semiWidth * EGG_ASPECT };
}

function constrainToEgg(nodes: SimNode[], cx: number, cy: number): void {
  const { semiWidth, semiHeight } = eggRadii(nodes.length);
  for (const n of nodes) {
    const dy = n.y - cy;
    const ny = Math.max(-1, Math.min(1, dy / semiHeight));
    if (Math.abs(dy) > semiHeight) {
      n.y = cy + Math.sign(dy) * semiHeight;
      n.vy = 0;
    }
    const halfWidth = eggHalfWidth(ny, semiWidth);
    const dx = n.x - cx;
    if (Math.abs(dx) > halfWidth) {
      n.x = cx + Math.sign(dx) * halfWidth;
      n.vx = 0;
    }
  }
}

function tick(nodes: SimNode[], edges: SimEdge[], alpha: number, cx: number, cy: number): void {
  const byKey = new Map(nodes.map((n) => [n.key, n]));
  const spacing = spacingFor(nodes.length);
  const linkDistance = LINK_DISTANCE * spacing;
  const repulsion = REPULSION * spacing * spacing;

  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i]!;
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j]!;
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let d = Math.hypot(dx, dy);
      if (d < MIN_DISTANCE) {
        if (d === 0) { dx = 1; dy = 1; d = Math.SQRT2; }
        d = MIN_DISTANCE;
      }
      const force = (repulsion * alpha) / (d * d);
      const fx = (dx / d) * force;
      const fy = (dy / d) * force;
      a.vx -= fx; a.vy -= fy;
      b.vx += fx; b.vy += fy;
    }
  }

  for (const edge of edges) {
    const a = byKey.get(edge.from);
    const b = byKey.get(edge.to);
    if (!a || !b) continue;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const d = Math.max(MIN_DISTANCE, Math.hypot(dx, dy));
    const force = (d - linkDistance) * LINK_STRENGTH * alpha;
    const fx = (dx / d) * force;
    const fy = (dy / d) * force;
    a.vx += fx; a.vy += fy;
    b.vx -= fx; b.vy -= fy;
  }

  for (const n of nodes) {
    n.vx += (cx - n.x) * CENTER_PULL * alpha;
    n.vy += (cy - n.y) * CENTER_PULL * alpha;
    n.vx *= DAMPING;
    n.vy *= DAMPING;
    n.x += n.vx;
    n.y += n.vy;
  }

  constrainToEgg(nodes, cx, cy);
}

/** Runs the layout to a standstill in one go, mutating `nodes`. Done synchronously rather than
 * animated frame by frame: at this size (tens of nodes) it costs well under a tenth of a second,
 * and it means there is nothing here that ever needs a prefers-reduced-motion check. */
export function settle(nodes: SimNode[], edges: SimEdge[], cx = 0, cy = 0): void {
  let alpha = 1;
  while (alpha > 0.004) {
    tick(nodes, edges, alpha, cx, cy);
    alpha *= 0.985;
  }
}

/** Deterministic starting positions on the egg's own outline, so the same data always settles
 * into the same picture. */
export function seedPositions(keys: string[], cx: number, cy: number): SimNode[] {
  const { semiWidth, semiHeight } = eggRadii(keys.length);
  return keys.map((key, i) => {
    const angle = (i / Math.max(1, keys.length)) * Math.PI * 2;
    const ny = -Math.cos(angle);
    return {
      key,
      x: cx + Math.sin(angle) * eggHalfWidth(ny, semiWidth) * 0.92,
      y: cy + ny * semiHeight * 0.92,
      vx: 0,
      vy: 0,
    };
  });
}
