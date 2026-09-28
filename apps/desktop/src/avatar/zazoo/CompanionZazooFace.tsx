/**
 * CompanionZazooFace — the desktop companion's collapsed face (Zazoo v1,
 * per docs/wiki/desktop-companion.md: "v1 = default in AvatarOverlay +
 * status→emotion map + capture-blink tell").
 *
 * Crops the full-body ZazooAvatar (portrait 240×310) to a square head shot
 * for the ~44px collapsed slot. ZazooAvatar declares `overflow: visible` on
 * its own <svg>, so THIS wrapper is the clip — without it the body and tail
 * spill past the 96px Tauri window edge.
 *
 * Honors `prefers-reduced-motion` with the static ZazooCompact head — the
 * director's spring/blink/breath loop never runs for those users. (The old
 * AvatarFigure overlay hardcoded reducedMotion={false}; this fixes that
 * inconsistency instead of copying it.)
 */
import { useEffect, useState } from "react";
import { ZazooAvatar } from "./ZazooAvatar";
import { ZazooCompact } from "./ZazooCompact";
import type { ZazooDirector } from "./director";

/** Full-body width that puts the head nicely inside a square crop of `size`. */
const BODY_WIDTH_RATIO = 64 / 44;
/** Nudge the crop window down so it centers on the face, not the ear tips. */
const HEAD_OFFSET_RATIO = -6 / 44;

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/** Portrait aspect of the full-body ZazooAvatar artboard (viewBox 240×310). */
const FULL_BODY_ASPECT = 240 / 310;

export function CompanionZazooFace({
  director,
  size = 44,
  label,
  /** `false` shows the whole animal (body, tail, gestures) letterboxed into a
   * `size` box instead of the square head crop — the collapsed overlay uses
   * this so hops, waves and tail motion are actually visible. */
  crop = true,
}: {
  director: ZazooDirector;
  size?: number;
  label: string;
  crop?: boolean;
}) {
  const reducedMotion = usePrefersReducedMotion();
  if (reducedMotion) {
    return (
      <div role="img" aria-label={label}>
        <ZazooCompact size={size} />
      </div>
    );
  }
  if (!crop) {
    return (
      <div
        role="img"
        aria-label={label}
        style={{
          width: size,
          height: size,
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-end",
        }}
      >
        <ZazooAvatar director={director} width={size * FULL_BODY_ASPECT} />
      </div>
    );
  }
  return (
    <div
      role="img"
      aria-label={label}
      style={{
        width: size,
        height: size,
        overflow: "hidden",
        display: "flex",
        justifyContent: "center",
        alignItems: "flex-start",
      }}
    >
      <div style={{ marginTop: size * HEAD_OFFSET_RATIO }}>
        <ZazooAvatar director={director} width={size * BODY_WIDTH_RATIO} />
      </div>
    </div>
  );
}
