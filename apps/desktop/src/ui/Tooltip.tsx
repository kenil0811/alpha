import * as RTooltip from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";
import "./Tooltip.css";

export const TooltipProvider = RTooltip.Provider;

/** Wraps a single child with a hover/focus tooltip. Use instead of a title= attribute. */
export function Tooltip({ content, children, side = "top" }: { content: ReactNode; children: ReactNode; side?: "top" | "right" | "bottom" | "left" }) {
  return (
    <RTooltip.Root delayDuration={300}>
      <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
      <RTooltip.Portal>
        <RTooltip.Content className="ui-tooltip" side={side} sideOffset={6}>
          {content}
          <RTooltip.Arrow className="ui-tooltip__arrow" />
        </RTooltip.Content>
      </RTooltip.Portal>
    </RTooltip.Root>
  );
}
