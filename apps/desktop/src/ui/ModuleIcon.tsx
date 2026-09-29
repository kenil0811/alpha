import { Boxes, type LucideIcon } from "lucide-react";

/** A module's lucide icon inline with its name (Boxes when it has none). */
export function ModuleIcon({ icon: Icon = Boxes, size = 14 }: { icon?: LucideIcon; size?: number }) {
  return <Icon size={size} strokeWidth={1.75} aria-hidden="true" style={{ verticalAlign: "-2px" }} />;
}
