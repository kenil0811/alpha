import { createContext, useContext, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
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

type Control = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

function isEmpty(el: Control): boolean {
  if (el instanceof HTMLInputElement && (el.type === "checkbox" || el.type === "radio")) return false;
  return String(el.value ?? "").trim() === "";
}

function labelOf(form: HTMLFormElement, el: Control): string {
  const byFor = el.id ? form.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null;
  const text = byFor?.textContent ?? el.getAttribute("aria-label") ?? "this field";
  return text.replace(/\s*\*\s*$/, "").trim();
}

function listed(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function Form({ onSubmit, children, className, label }: FormProps) {
  const ref = useRef<HTMLFormElement>(null);
  const [missing, setMissing] = useState<string[]>([]);

  /** Required fields the person left empty. The kit checks them itself because the sandboxed
   *  frame forbids the browser's own form validation (M1 review: empty forms reached the App). */
  function emptyRequired(): Control[] {
    const form = ref.current;
    if (!form) return [];
    return Array.from(form.querySelectorAll<Control>('[aria-required="true"], [required]')).filter((el) => !el.disabled && isEmpty(el));
  }

  const submit = () => {
    const form = ref.current;
    const empty = emptyRequired();
    if (form && empty.length) {
      setMissing(empty.map((el) => labelOf(form, el)));
      empty.forEach((el) => el.setAttribute("aria-invalid", "true"));
      empty[0].focus();
      return;
    }
    setMissing([]);
    void Promise.resolve(onSubmit()).then(
      () => {
        // Ready for the next entry when the App cleared the form after saving (checked after
        // React has applied the App's state changes).
        window.setTimeout(() => {
          const first = form?.querySelector<Control>("input:not([type=hidden]):not([type=checkbox]):not([type=radio]), textarea");
          const inForm = form?.contains(document.activeElement ?? null) || document.activeElement === document.body;
          if (first && isEmpty(first) && inForm) first.focus();
        }, 0);
      },
      () => undefined, // the App shows its own failure; what was typed stays
    );
  };

  function onInput(event: FormEvent<HTMLFormElement>) {
    const target = event.target as Control;
    if (target.getAttribute("aria-invalid") === "true" && !isEmpty(target)) target.removeAttribute("aria-invalid");
    if (missing.length) {
      const form = ref.current;
      setMissing(form ? emptyRequired().map((el) => labelOf(form, el)) : []);
    }
  }
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
        ref={ref}
        className={cx("a-form", className)}
        noValidate
        aria-label={label}
        onKeyDown={onKeyDown}
        onInput={onInput}
        onSubmit={(event) => {
          // Outside a sandbox (tests, the reference sheet) a native submit may still happen.
          event.preventDefault();
          submit();
        }}
      >
        {children}
        {missing.length ? (
          <p className="a-form__missing" role="alert">
            Fill in {listed(missing)} first.
          </p>
        ) : null}
      </form>
    </FormContext.Provider>
  );
}
