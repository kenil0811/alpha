import { Info } from "lucide-react";
import { Tooltip, TooltipProvider } from "./Tooltip";

/** A small (i) affordance that reveals an explainer on hover/focus. Use next to a title/label
 * instead of a description sentence under it — keeps the surface scannable at a glance.
 * Carries its own TooltipProvider (Radix allows nesting) so it renders standalone in tests
 * that mount a component without the app's own top-level provider. */
export function InfoTip({ content, label = "More info" }: { content: string; label?: string }) {
  return (
    <TooltipProvider>
      <Tooltip content={content}>
        <button type="button" className="ui-infotip" aria-label={label}>
          <Info size={14} aria-hidden="true" />
        </button>
      </Tooltip>
    </TooltipProvider>
  );
}
