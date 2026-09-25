import { createContext, useContext, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "./layout";

/**
 * Generated UI runs in a frame sandboxed WITHOUT `allow-forms`: the browser aborts native form
 * submission before any `submit` event fires (HTML form submission algorithm, sandboxed forms
 * flag). A plain `<form onSubmit>` therefore never saves. `Form` does the submitting itself:
 * Enter in a single-line field and activating a kit submit `Button` both call `onSubmit`.
 * Always use `Form` (not `<form>`) in App UI.
 */
const FormContext = createContext<(() => void) | null>(null);

export function useFormSubmit(): (() => void) | null {
  return useContext(FormContext);
}

const NON_TEXT_INPUTS = new Set(["checkbox", "radio", "button", "submit", "reset", "file", "range", "color"]);

export interface FormProps {
  onSubmit: () => void | Promise<void>;
  children: ReactNode;
  className?: string;
  /** Accessible name for the form region, when the surrounding heading does not name it. */
  label?: string;
}

export function Form({ onSubmit, children, className, label }: FormProps) {
  const submit = () => void onSubmit();
  function onKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.altKey || event.metaKey || event.ctrlKey || event.nativeEvent.isComposing) return;
    const target = event.target;
    if (target instanceof HTMLInputElement && !NON_TEXT_INPUTS.has(target.type)) {
      event.preventDefault();
      submit();
    }
  }
  return (
    <FormContext.Provider value={submit}>
      <form
        className={cx("a-form", className)}
        noValidate
        aria-label={label}
        onKeyDown={onKeyDown}
        onSubmit={(event) => {
          // Outside a sandbox (tests, the reference sheet) a native submit may still happen.
          event.preventDefault();
          submit();
        }}
      >
        {children}
      </form>
    </FormContext.Provider>
  );
}
