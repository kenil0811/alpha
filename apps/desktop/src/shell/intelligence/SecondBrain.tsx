import type { LucideIcon } from "lucide-react";
/**
 * Second brain: an egg-shaped force-directed graph of what Alpha actually holds — every
 * installed module, every fact it knows about the person, and the real links between them
 * (a module reading another, a fact that arrived from a module). Adapted from the CV Naturals
 * project's Intelligence page (`apps/web/src/pages/intelligence/IntelligencePage.tsx` — same
 * author, lawful reuse), whose "products / materials / plants" graph becomes "modules / facts"
 * here; the layout math is `./forceLayout.ts`, ported from that project's `lib/forceLayout.ts`.
 *
 * Real data or nothing: a module with no facts and no links still gets a dot, but nothing is
 * invented to make the picture busier. No modules and no facts is an honest empty state, not an
 * empty egg.
 */
import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { type AppSummary, type CoreClient, type ModuleConnection, type ProfileFact, isConnectionsClient, isProfileClient } from "../../core/client";
import { humanize } from "../../modules/useModule";
import { eggHalfWidth, eggRadii, seedPositions, settle, type SimEdge, type SimNode } from "./forceLayout";
import { shown } from "./shared";

interface GraphNode {
  key: string;
  label: string;
  kind: "module" | "fact";
  /** What clicking the node opens. */
  open: () => void;
}

const COLORS: Record<GraphNode["kind"], string> = { module: "var(--primary)", fact: "var(--bridge-sage)" };
const KIND_LABEL: Record<GraphNode["kind"], string> = { module: "Modules", fact: "Facts" };

const VIEW_W = 640;
const VIEW_H = 640 * 1.32;
/** A drag that never moves more than this many screen pixels is a tap, not a pan. */
const TAP_SLOP = 6;

export function SecondBrain({ client, modules, onOpenModule, onOpenAbout }: { client: CoreClient; modules: AppSummary[]; icons: Record<string, LucideIcon>; onOpenModule: (appId: string) => void; onOpenAbout: () => void }) {
  const [facts, setFacts] = useState<ProfileFact[] | null>(null);
  const [pending, setPending] = useState(0);
  const [links, setLinks] = useState<{ from: string; module: string }[]>([]);

  useEffect(() => {
    if (!isProfileClient(client)) {
      setFacts([]);
      return;
    }
    let cancelled = false;
    client
      .profile()
      .then((view) => {
        if (cancelled) return;
        setFacts(view.facts);
        setPending(view.suggestions.length);
      })
      .catch(() => {
        if (!cancelled) setFacts([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  // Real module-to-module links only — the same declared, switchable connections Intelligence's
  // Connections tab shows (see ModuleLinks.tsx). A link that isn't installed or switched on still
  // shows here: it's a real declared relationship, whether or not it's live right now.
  useEffect(() => {
    if (!isConnectionsClient(client) || !modules.length) {
      setLinks([]);
      return;
    }
    let cancelled = false;
    Promise.all(modules.map((m) => client.connections(m.app_id).then((all: ModuleConnection[]) => all.map((l) => ({ from: m.app_id, module: l.module }))).catch(() => [])))
      .then((groups) => {
        if (!cancelled) setLinks(groups.flat());
      })
      .catch(() => {
        if (!cancelled) setLinks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [client, modules]);

  const loaded = facts !== null;
  const nodes = useMemo<GraphNode[]>(() => {
    if (!loaded) return [];
    const moduleNodes: GraphNode[] = modules.map((m) => ({ key: `module:${m.app_id}`, label: m.name, kind: "module", open: () => onOpenModule(m.app_id) }));
    const factNodes: GraphNode[] = (facts ?? []).map((f) => ({ key: `fact:${f.fact_id}`, label: `${humanize(f.field)}: ${shown(f.value)}`, kind: "fact", open: onOpenAbout }));
    return [...moduleNodes, ...factNodes];
  }, [loaded, modules, facts, onOpenModule, onOpenAbout]);

  const edges = useMemo<SimEdge[]>(() => {
    const present = new Set(nodes.map((n) => n.key));
    const list: SimEdge[] = [];
    for (const link of links) {
      const from = `module:${link.from}`;
      const to = `module:${link.module}`;
      if (present.has(from) && present.has(to)) list.push({ from, to });
    }
    // A fact that arrived from a module is a real, recorded link to it — not every fact has one.
    for (const f of facts ?? []) {
      if (f.provenance !== "module") continue;
      const from = `fact:${f.fact_id}`;
      const to = `module:${f.source}`;
      if (present.has(from) && present.has(to)) list.push({ from, to });
    }
    return list;
  }, [nodes, links, facts]);

  // A plain state array, not a ref: the layout only ever settles once per data change (no
  // per-frame dragging, see forceLayout.ts), so there's no 60fps mutation to keep out of React.
  const [positions, setPositions] = useState<SimNode[]>([]);
  useEffect(() => {
    const seeded = seedPositions(nodes.map((n) => n.key), 0, 0);
    settle(seeded, edges);
    setPositions(seeded);
  }, [nodes, edges]);
  const posOf = (key: string) => positions.find((n) => n.key === key);

  const eggPath = useMemo(() => {
    const { semiWidth, semiHeight } = eggRadii(nodes.length);
    const steps = 80;
    const right: string[] = [];
    const left: string[] = [];
    for (let i = 0; i <= steps; i++) {
      const ny = -1 + (2 * i) / steps;
      const halfWidth = eggHalfWidth(ny, semiWidth);
      const y = ny * semiHeight;
      right.push(`${halfWidth.toFixed(1)},${y.toFixed(1)}`);
      left.push(`${(-halfWidth).toFixed(1)},${y.toFixed(1)}`);
    }
    return `M ${right.join(" L ")} L ${left.reverse().join(" L ")} Z`;
  }, [nodes.length]);

  const degree = useMemo(() => {
    const counts = new Map<string, number>();
    for (const e of edges) {
      counts.set(e.from, (counts.get(e.from) ?? 0) + 1);
      counts.set(e.to, (counts.get(e.to) ?? 0) + 1);
    }
    return counts;
  }, [edges]);

  const [selectedKind, setSelectedKind] = useState<GraphNode["kind"] | null>(null);
  const focus = useMemo(() => (selectedKind ? new Set(nodes.filter((n) => n.kind === selectedKind).map((n) => n.key)) : null), [selectedKind, nodes]);

  // Fit the whole settled graph (plus the shell) into view once it's laid out.
  const [view, setView] = useState({ x: -VIEW_W / 2, y: -VIEW_H / 2, w: VIEW_W, h: VIEW_H });
  const fitToGraph = () => {
    const { semiWidth, semiHeight } = eggRadii(nodes.length);
    const pad = 40;
    const w = semiWidth * 2 + pad * 2;
    const h = semiHeight * 2 + pad * 2;
    setView({ x: -w / 2, y: -h / 2, w, h });
  };
  useEffect(() => {
    if (nodes.length) fitToGraph();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length]);
  const zoomTo = (width: number) => setView((v) => ({ ...v, w: Math.max(160, Math.min(VIEW_W * 3, width)), h: v.h * (Math.max(160, Math.min(VIEW_W * 3, width)) / v.w) }));

  // Panning the background; a plain pointer drag, no per-node dragging (see forceLayout.ts).
  const svgRef = useRef<SVGSVGElement>(null);
  const panFrom = useRef<{ x: number; y: number } | null>(null);
  const moved = useRef(0);
  const onPointerDown = (e: PointerEvent) => {
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    panFrom.current = { x: e.clientX, y: e.clientY };
    moved.current = 0;
  };
  const onPointerMove = (e: PointerEvent) => {
    const from = panFrom.current;
    if (!from) return;
    const px = view.w / (svgRef.current?.clientWidth || VIEW_W);
    const dx = (e.clientX - from.x) * px;
    const dy = (e.clientY - from.y) * px;
    moved.current += Math.hypot(e.clientX - from.x, e.clientY - from.y);
    panFrom.current = { x: e.clientX, y: e.clientY };
    setView((v) => ({ ...v, x: v.x - dx, y: v.y - dy }));
  };
  const onPointerUp = () => {
    panFrom.current = null;
  };

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn btn--sm" onClick={onOpenAbout}>
          {pending ? `Manage (${pending} waiting for you)` : "Manage what Alpha knows"}
        </button>
      </div>
      {!loaded ? (
        <p className="faint">Loading…</p>
      ) : nodes.length === 0 ? (
        <p className="empty">Nothing yet.</p>
      ) : (
        <div className="card intel-graph-card">
          <div className="intel-controls">
            {(["module", "fact"] as const).map((kind) => (
              <button
                key={kind}
                type="button"
                className={"intel-legend" + (selectedKind === kind ? " active" : "")}
                aria-pressed={selectedKind === kind}
                onClick={() => setSelectedKind((k) => (k === kind ? null : kind))}
              >
                <span className="intel-swatch" style={{ background: COLORS[kind] }} />
                {KIND_LABEL[kind]}
              </button>
            ))}
            <span style={{ flex: 1 }} />
            <button type="button" className="btn btn--sm" onClick={() => zoomTo(view.w / 1.3)} title="Zoom in">＋</button>
            <button type="button" className="btn btn--sm" onClick={() => zoomTo(view.w * 1.3)} title="Zoom out">－</button>
            <button type="button" className="btn btn--sm" onClick={fitToGraph} title="Back to the starting view">Reset</button>
          </div>
          <svg
            ref={svgRef}
            className="intel-graph"
            role="img"
            aria-label="Second brain graph"
            viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onWheel={(e) => zoomTo(view.w * (e.deltaY > 0 ? 1.1 : 1 / 1.1))}
            style={{ touchAction: "none" }}
          >
            <path d={eggPath} fill="none" stroke="var(--border)" strokeWidth={1.2} opacity={0.6} style={{ pointerEvents: "none" }} />
            {edges.map((e, i) => {
              const a = posOf(e.from);
              const b = posOf(e.to);
              if (!a || !b) return null;
              const inFocus = !focus || focus.has(e.from) || focus.has(e.to);
              return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--border)" strokeWidth={1} opacity={inFocus ? 1 : 0.15} />;
            })}
            {nodes.map((n) => {
              const p = posOf(n.key);
              if (!p) return null;
              const r = 6 + Math.min(8, (degree.get(n.key) ?? 0) * 1.4);
              const inFocus = !focus || focus.has(n.key);
              return (
                <g
                  key={n.key}
                  transform={`translate(${p.x},${p.y})`}
                  style={{ cursor: "pointer" }}
                  opacity={inFocus ? 1 : 0.2}
                  onPointerUp={() => {
                    if (moved.current < TAP_SLOP) n.open();
                  }}
                >
                  <circle r={r} fill={COLORS[n.kind]} stroke="var(--surface)" strokeWidth={1.5} />
                  <text y={r + 12} textAnchor="middle" fill="var(--text)" fontSize={11}>
                    {n.label}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </div>
  );
}
