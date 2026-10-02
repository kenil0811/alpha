import * as RDropdown from "@radix-ui/react-dropdown-menu";
import "./DropdownMenu.css";

export const DropdownMenu = RDropdown.Root;
export const DropdownMenuTrigger = RDropdown.Trigger;
export const DropdownMenuSub = RDropdown.Sub;

export function DropdownMenuSubTrigger({ className = "", ...rest }: RDropdown.DropdownMenuSubTriggerProps) {
  return <RDropdown.SubTrigger className={`ui-menu__item ui-menu__item--sub ${className}`.trim()} {...rest} />;
}

export function DropdownMenuSubContent({ children }: { children: React.ReactNode }) {
  return (
    <RDropdown.Portal>
      <RDropdown.SubContent className="ui-menu ui-menu--sub" sideOffset={2} alignOffset={-4}>
        {children}
      </RDropdown.SubContent>
    </RDropdown.Portal>
  );
}

export function DropdownMenuContent({ children, align = "start" }: { children: React.ReactNode; align?: "start" | "center" | "end" }) {
  return (
    <RDropdown.Portal>
      <RDropdown.Content className="ui-menu" align={align} sideOffset={4}>
        {children}
      </RDropdown.Content>
    </RDropdown.Portal>
  );
}

export function DropdownMenuItem({ className = "", ...rest }: RDropdown.DropdownMenuItemProps) {
  return <RDropdown.Item className={`ui-menu__item ${className}`.trim()} {...rest} />;
}

export function DropdownMenuCheckboxItem({ className = "", ...rest }: RDropdown.DropdownMenuCheckboxItemProps) {
  return <RDropdown.CheckboxItem className={`ui-menu__item ${className}`.trim()} {...rest} />;
}

export function DropdownMenuLabel({ className = "", ...rest }: RDropdown.DropdownMenuLabelProps) {
  return <RDropdown.Label className={`ui-menu__label ${className}`.trim()} {...rest} />;
}

export function DropdownMenuSeparator() {
  return <RDropdown.Separator className="ui-menu__sep" />;
}
