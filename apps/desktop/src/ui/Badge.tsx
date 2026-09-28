import type { HTMLAttributes } from "react";
import "./Badge.css";

export type BadgeVariant = "success" | "warning" | "danger" | "neutral" | "info" | "default";

export function Badge({ variant = "default", className = "", ...rest }: HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }) {
  return <span className={`ui-badge ui-badge--${variant} ${className}`.trim()} {...rest} />;
}
