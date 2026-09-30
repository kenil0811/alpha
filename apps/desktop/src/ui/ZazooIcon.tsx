import { useMemo } from "react";
import { CompanionZazooFace } from "../avatar/zazoo/CompanionZazooFace";
import { ZazooDirector } from "../avatar/zazoo/director";

/** Zazoo, the Chief of Staff, as a static icon — the same painted panda the floating
 *  companion (avatar/Character.tsx) shows, held on one resting frame and cropped to the
 *  head, so the rail mark, panel headers and module button all read as one character.
 *  (prefers-reduced-motion users see the plush ZazooCompact head, same as the companion.) */
export function ZazooIcon({ size = 32, className, label = "Chief of Staff" }: { size?: number; className?: string; label?: string }) {
  const director = useMemo(() => new ZazooDirector(), []);
  return (
    <span className={className} style={{ display: "block", width: size, height: size }}>
      <CompanionZazooFace director={director} size={size} label={label} crop animate={false} />
    </span>
  );
}
