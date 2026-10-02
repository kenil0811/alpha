import * as RDialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import "./Dialog.css";

export const Dialog = RDialog.Root;
export const DialogTrigger = RDialog.Trigger;

export function DialogContent({ children, title, description }: { children: React.ReactNode; title: string; description?: string }) {
  return (
    <RDialog.Portal>
      <RDialog.Overlay className="ui-dialog-overlay" />
      <RDialog.Content className="ui-dialog-content" aria-describedby={description ? undefined : undefined}>
        <div className="ui-dialog__head">
          <RDialog.Title className="ui-dialog__title">{title}</RDialog.Title>
          <RDialog.Close asChild>
            <button type="button" className="ui-iconbtn ui-iconbtn--sm" aria-label="Close">
              <X size={16} />
            </button>
          </RDialog.Close>
        </div>
        {description ? <RDialog.Description className="ui-dialog__desc">{description}</RDialog.Description> : null}
        {children}
      </RDialog.Content>
    </RDialog.Portal>
  );
}

export const DialogClose = RDialog.Close;
