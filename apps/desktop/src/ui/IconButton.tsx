import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";
import "./IconButton.css";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  "aria-label": string;
  size?: "sm" | "default";
}

/** A square icon-only button. Always requires aria-label — there is no visible text fallback. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { className = "", size = "default", type = "button", ...rest },
  ref,
) {
  return <button ref={ref} type={type} className={`ui-iconbtn ui-iconbtn--${size} ${className}`.trim()} {...rest} />;
});
