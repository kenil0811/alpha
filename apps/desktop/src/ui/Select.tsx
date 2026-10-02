import * as RSelect from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import "./Select.css";

export const Select = RSelect.Root;

export function SelectTrigger({ className = "" }: { className?: string }) {
  return (
    <RSelect.Trigger className={`ui-select-trigger ${className}`.trim()}>
      <RSelect.Value />
      <RSelect.Icon>
        <ChevronDown size={14} />
      </RSelect.Icon>
    </RSelect.Trigger>
  );
}

export function SelectContent({ children }: { children: React.ReactNode }) {
  return (
    <RSelect.Portal>
      <RSelect.Content className="ui-select-content" position="popper" sideOffset={4}>
        <RSelect.Viewport>{children}</RSelect.Viewport>
      </RSelect.Content>
    </RSelect.Portal>
  );
}

export function SelectItem({ children, value, ...rest }: RSelect.SelectItemProps) {
  return (
    <RSelect.Item className="ui-select-item" value={value} {...rest}>
      <RSelect.ItemText>{children}</RSelect.ItemText>
      <RSelect.ItemIndicator className="ui-select-item__check">
        <Check size={14} />
      </RSelect.ItemIndicator>
    </RSelect.Item>
  );
}
