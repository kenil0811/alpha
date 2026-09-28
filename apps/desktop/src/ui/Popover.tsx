import * as RPopover from "@radix-ui/react-popover";
import "./Popover.css";

export const Popover = RPopover.Root;
export const PopoverTrigger = RPopover.Trigger;

export function PopoverContent({ children, align = "start" }: { children: React.ReactNode; align?: "start" | "center" | "end" }) {
  return (
    <RPopover.Portal>
      <RPopover.Content className="ui-popover" align={align} sideOffset={6}>
        {children}
        <RPopover.Arrow className="ui-popover__arrow" />
      </RPopover.Content>
    </RPopover.Portal>
  );
}
