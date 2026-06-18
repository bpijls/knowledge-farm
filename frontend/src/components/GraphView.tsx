import { useCallback, useEffect, useMemo, useRef } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { forceCollide } from "d3-force-3d";
import type { GraphData } from "../types";

interface Props {
  data: GraphData;
  seedIds: Set<string>;
  showLabels: boolean;
  selectedId: string | null;
  pathIds: Set<string>;
  pathEdges: Set<string>;
  onSelectNode: (id: string | null) => void;
}

// Germination spectrum: a planted seed (amber) sends growth outward, maturing
// from leaf-green through teal to a violet bloom at the deepest generations.
// Tuned dark/saturated enough to read against the pale daylight field.
function nodeColor(depth: number, isSeed: boolean): string {
  if (isSeed) return "#e0922a"; // sun amber — a planted seed
  const hue = Math.min(95 + (depth - 1) * 32, 285); // leaf-green → violet bloom
  return `hsl(${hue}, 62%, 46%)`;
}

const REDUCE_MOTION =
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const GERMINATE_MS = 520; // how long a node takes to sprout to full size

function visualRadius(isSeed: boolean, deg: number): number {
  return isSeed ? 10 : Math.max(4, Math.min(4 + deg * 0.8, 12));
}

// Collision radius keeps node centers apart so each gets its own hit region.
function collideRadius(isSeed: boolean, deg: number): number {
  return visualRadius(isSeed, deg) + 6;
}

export function GraphView({
  data,
  seedIds,
  showLabels,
  selectedId,
  pathIds,
  pathEdges,
  onSelectNode,
}: Props) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<any>(null);
  // Tracks a press to distinguish a click (select) from a drag (move) / pan.
  const pressRef = useRef<{ x: number; y: number; moved: boolean; node: any } | null>(null);
  const onSelectRef = useRef(onSelectNode);
  onSelectRef.current = onSelectNode;

  const degree = useMemo(() => {
    const map = new Map<string, number>();
    for (const e of data.edges) {
      map.set(e.source, (map.get(e.source) ?? 0) + 1);
      map.set(e.target, (map.get(e.target) ?? 0) + 1);
    }
    return map;
  }, [data.edges]);

  const graphData = useMemo(
    () => ({
      nodes: data.nodes.map((n) => ({ ...n, name: n.label })),
      links: data.edges.map((e) => ({ source: e.source, target: e.target })),
    }),
    [data],
  );

  // The canvas only exists once there are nodes to render (see early return).
  const hasGraph = graphData.nodes.length > 0;

  // Latest values accessible from the bound-once pointer listeners below.
  const nodesRef = useRef<any[]>([]);
  nodesRef.current = graphData.nodes;
  const degreeRef = useRef(degree);
  degreeRef.current = degree;
  const seedRef = useRef(seedIds);
  seedRef.current = seedIds;

  // Records when each node first appeared so paintNode can sprout it in.
  const birthRef = useRef<Map<string, number>>(new Map());

  // Coordinate-based dragging. We do NOT use force-graph's built-in node drag
  // because it identifies the target by reading a pixel off an offscreen "shadow"
  // canvas — and Brave's fingerprinting protection ("farbling") adds noise to
  // canvas readback, corrupting the per-node index color so the lookup always
  // fails and every press becomes a pan. Hit-testing in graph coordinates instead
  // works in every browser. node.x/y are read live on each press, so this stays
  // correct even while the force simulation is animating.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const canvas = container.querySelector("canvas");
    if (!canvas) return;

    const hitRadius = (n: any): number => {
      const isSeed = seedRef.current.has(n.id);
      const deg = degreeRef.current.get(n.id) ?? 0;
      const scale = fgRef.current?.zoom?.() ?? 1;
      // At least 12 screen px of grab area, expressed in graph units.
      return Math.max(visualRadius(isSeed, deg), 12 / scale);
    };

    const nodeAt = (clientX: number, clientY: number): any => {
      const fg = fgRef.current;
      if (!fg) return null;
      const rect = canvas.getBoundingClientRect();
      const gp = fg.screen2GraphCoords(clientX - rect.left, clientY - rect.top);
      let best: any = null;
      let bestD = Infinity;
      for (const n of nodesRef.current) {
        if (n.x == null || n.y == null) continue;
        const dx = n.x - gp.x;
        const dy = n.y - gp.y;
        const d2 = dx * dx + dy * dy;
        const r = hitRadius(n);
        if (d2 <= r * r && d2 < bestD) {
          bestD = d2;
          best = n;
        }
      }
      return best;
    };

    // Pointer position from a mouse or touch event (in client coordinates).
    const getXY = (ev: MouseEvent | TouchEvent): { x: number; y: number } | null => {
      if ("touches" in ev) {
        const t = ev.touches[0] ?? ev.changedTouches[0];
        return t ? { x: t.clientX, y: t.clientY } : null;
      }
      return { x: ev.clientX, y: ev.clientY };
    };

    const onStart = (ev: MouseEvent | TouchEvent) => {
      const xy = getXY(ev);
      if (!xy) return;
      const node = nodeAt(xy.x, xy.y);
      // Record the press so onEnd can tell a click (no movement) from a drag/pan.
      pressRef.current = { x: xy.x, y: xy.y, moved: false, node };
      if (!node) return; // background → let force-graph (d3-zoom) pan
      // Block d3-zoom — it binds "mousedown.zoom"/"touchstart.zoom" on the canvas;
      // capture phase on the container runs first, so stopPropagation prevents the
      // pan and lets us drag the node instead.
      ev.stopPropagation();
      ev.preventDefault();
      dragRef.current = node;
      node.fx = node.x;
      node.fy = node.y;
      fgRef.current?.d3ReheatSimulation?.();
      fgRef.current?.d3AlphaTarget?.(0.3); // keep the render loop alive while dragging
    };

    const onMove = (ev: MouseEvent | TouchEvent) => {
      const xy = getXY(ev);
      const press = pressRef.current;
      if (press && xy && !press.moved) {
        const dx = xy.x - press.x;
        const dy = xy.y - press.y;
        if (dx * dx + dy * dy > 16) press.moved = true; // > 4px → it's a drag/pan
      }
      const node = dragRef.current;
      if (!node || !xy) return;
      ev.preventDefault(); // suppress text selection / touch scroll
      const rect = canvas.getBoundingClientRect();
      const gp = fgRef.current.screen2GraphCoords(xy.x - rect.left, xy.y - rect.top);
      node.fx = node.x = gp.x;
      node.fy = node.y = gp.y;
    };

    const onEnd = () => {
      const press = pressRef.current;
      pressRef.current = null;

      const node = dragRef.current;
      if (node) {
        dragRef.current = null;
        // Release the node back into the simulation so the force-direction physics
        // resumes (the node settles into the layout instead of staying fixed).
        node.fx = undefined;
        node.fy = undefined;
        fgRef.current?.d3AlphaTarget?.(0); // stop forcing the engine; let it cool
      }

      // A press that didn't move is a click: select the node under it, or clear
      // the selection when clicking empty background.
      if (press && !press.moved) {
        onSelectRef.current(press.node ? press.node.id : null);
      }
    };

    const onHover = (ev: MouseEvent) => {
      if (dragRef.current) return;
      canvas.style.cursor = nodeAt(ev.clientX, ev.clientY) ? "grab" : "default";
    };

    const cap = { capture: true } as const;
    const capActive = { capture: true, passive: false } as const;
    container.addEventListener("mousedown", onStart, cap);
    container.addEventListener("touchstart", onStart, capActive);
    window.addEventListener("mousemove", onMove, cap);
    window.addEventListener("touchmove", onMove, capActive);
    window.addEventListener("mouseup", onEnd, cap);
    window.addEventListener("touchend", onEnd, cap);
    canvas.addEventListener("mousemove", onHover);
    return () => {
      container.removeEventListener("mousedown", onStart, cap);
      container.removeEventListener("touchstart", onStart, capActive);
      window.removeEventListener("mousemove", onMove, cap);
      window.removeEventListener("touchmove", onMove, capActive);
      window.removeEventListener("mouseup", onEnd, cap);
      window.removeEventListener("touchend", onEnd, cap);
      canvas.removeEventListener("mousemove", onHover);
    };
  }, [hasGraph]);

  // Add a collision force so overlapping nodes spread apart, and reheat the
  // simulation so the layout rearranges as new nodes stream in.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    // Stamp newly-arrived nodes so they germinate; the reheat below keeps the
    // canvas repainting for long enough to play the sprout-in.
    const now = performance.now();
    for (const n of graphData.nodes) {
      if (!birthRef.current.has(n.id)) birthRef.current.set(n.id, now);
    }
    fg.d3Force(
      "collide",
      forceCollide((node: any) => {
        const isSeed = seedIds.has(node.id);
        const deg = degree.get(node.id) ?? 0;
        return collideRadius(isSeed, deg);
      }),
    );
    fg.d3ReheatSimulation();
  }, [graphData, degree, seedIds]);

  // Visual rendering — paints our custom node circles. Hit-testing is handled
  // separately in graph coordinates (see the pointer effect above), not via the
  // shadow canvas, so this only needs to draw.
  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D) => {
      const isSeed = seedIds.has(node.id);
      const deg = degree.get(node.id) ?? 0;
      const hasSelection = selectedId !== null;
      const onPath = pathIds.has(node.id);
      const isSelected = node.id === selectedId;

      // Germinate: ease the radius and opacity up over a node's first moments
      // so each new concept visibly sprouts as the generation streams in.
      let grow = 1;
      if (!REDUCE_MOTION) {
        const birth = birthRef.current.get(node.id);
        if (birth != null) {
          const t = Math.min((performance.now() - birth) / GERMINATE_MS, 1);
          grow = 1 - Math.pow(1 - t, 3); // easeOutCubic
        }
      }
      const r = visualRadius(isSeed, deg) * (0.45 + 0.55 * grow);

      // Dim nodes off the highlighted lineage; sprouting nodes fade in.
      const dim = hasSelection && !onPath ? 0.18 : 1;
      ctx.globalAlpha = dim * (REDUCE_MOTION ? 1 : 0.25 + 0.75 * grow);

      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = nodeColor(node.depth, isSeed);
      ctx.fill();
      if (isSeed) {
        ctx.strokeStyle = "#b5701a"; // amber edge — a planted seed
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      // Ring the selected node (ink) and the rest of the lineage (sky blue).
      if (isSelected || onPath) {
        ctx.strokeStyle = isSelected ? "#22281c" : "#2e7fb0";
        ctx.lineWidth = isSelected ? 3 : 2;
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 2.5, 0, 2 * Math.PI);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    },
    [degree, seedIds, selectedId, pathIds],
  );

  // Draw all labels in a second pass so no node circle paints over another node's text.
  const paintLabels = useCallback(
    (ctx: CanvasRenderingContext2D) => {
      ctx.save();
      ctx.textAlign = "center";
      for (const node of graphData.nodes as any[]) {
        if (node.x == null || node.y == null) continue;
        const isSeed = seedIds.has(node.id);
        const deg = degree.get(node.id) ?? 0;
        const onPath = pathIds.has(node.id);
        // Always label path nodes; otherwise only seeds / hubs when labels are on.
        if (!onPath && (!showLabels || (!isSeed && deg < 3))) continue;
        const r = visualRadius(isSeed, deg);
        ctx.fillStyle = onPath ? "#22281c" : "#46523a";
        ctx.font = `${isSeed || onPath ? 600 : 400} ${isSeed || onPath ? 11 : 9}px "IBM Plex Sans", sans-serif`;
        ctx.fillText(node.label, node.x, node.y + r + 9);
      }
      ctx.restore();
    },
    [graphData.nodes, degree, seedIds, showLabels, pathIds],
  );

  // Once the simulation cools, the canvas stops redrawing on its own. When the
  // label toggle or the selection/path changes, force a single repaint WITHOUT
  // reheating the physics (which would shift the settled layout): re-applying the
  // current zoom marks the canvas as needing a redraw.
  useEffect(() => {
    const fg = fgRef.current;
    if (fg) fg.zoom(fg.zoom(), 0);
  }, [showLabels, selectedId, pathIds]);

  // Scale/center the graph to fit the viewport — triggered manually via the
  // "Fit" button rather than automatically when the layout settles.
  const fitView = useCallback(() => {
    fgRef.current?.zoomToFit(400, 40);
  }, []);

  const linkOnPath = useCallback(
    (link: any) => {
      const s = typeof link.source === "object" ? link.source.id : link.source;
      const t = typeof link.target === "object" ? link.target.id : link.target;
      return pathEdges.has(`${s}|${t}`);
    },
    [pathEdges],
  );

  const linkColor = useCallback(
    (link: any) => {
      if (linkOnPath(link)) return "#2e7fb0"; // sky — the active lineage
      // Stem green, kept clearly visible against the pale field.
      return selectedId !== null ? "rgba(70,82,58,0.1)" : "rgba(70,82,58,0.4)";
    },
    [linkOnPath, selectedId],
  );

  const linkWidth = useCallback(
    (link: any) => (linkOnPath(link) ? 3 : 1.3),
    [linkOnPath],
  );

  if (data.nodes.length === 0) return null;

  return (
    <div className="graph-container" ref={containerRef}>
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        nodeId="id"
        nodeCanvasObject={paintNode}
        nodeCanvasObjectMode={() => "replace"}
        onRenderFramePost={paintLabels}
        linkColor={linkColor}
        linkWidth={linkWidth}
        backgroundColor="#e8eedd"
        cooldownTicks={120}
        enableNodeDrag={false}
        enablePointerInteraction={false}
      />
      <button className="fit-btn" onClick={fitView} title="Scale graph to fit">
        Fit
      </button>
      <div className="legend">
        <span className="legend-seed">● Seed</span>
        <span className="legend-d1">● Sprout</span>
        <span className="legend-d2">● Bloom</span>
      </div>
    </div>
  );
}
