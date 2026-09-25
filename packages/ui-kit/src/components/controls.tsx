import {
  forwardRef,
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { useFormSubmit } from "./Form";
import { cx } from "./layout";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  small?: boolean;
  /** While true the button is disabled, marked busy and shows `busyLabel`. */
  busy?: boolean;
  busyLabel?: string;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", small = false, busy = false, busyLabel = "Working…", children, className, disabled, type, onClick, ...rest },
  ref,
) {
  // Inside a kit Form, a submit button submits through the Form (sandboxed frames never fire
  // native submit events); it is a plain button to the browser.
  const formSubmit = useFormSubmit();
  const viaForm = type === "submit" && formSubmit !== null;
  return (
    <button
      ref={ref}
      type={viaForm ? "button" : (type ?? "button")}
      onClick={(event) => {
        onClick?.(event);
        if (viaForm && !event.defaultPrevented) formSubmit();
      }}
      className={cx("a-button", variant !== "secondary" && `a-button--${variant}`, small && "a-button--small", className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? busyLabel : children}
    </button>
  );
});

export interface FieldControlProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
  "aria-required"?: boolean;
}

export interface FieldProps {
  label: string;
  hint?: ReactNode;
  /** A validation or save error for this field; shown under it and announced. */
  error?: string | null;
  required?: boolean;
  children: (control: FieldControlProps) => ReactNode;
}

/** Label, hint and error wiring for any control. The render function receives the ids. */
export function Field({ label, hint, error, required, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="a-field">
      <label className="a-field__label" htmlFor={id}>
        {label}
        {required ? (
          <span className="a-field__required" aria-hidden="true">
            *
          </span>
        ) : null}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined, "aria-required": required || undefined })}
      {hint ? (
        <span className="a-field__hint" id={hintId}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span className="a-field__error" id={errorId} role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}

type Common = { label: string; hint?: ReactNode; error?: string | null; required?: boolean };

export const TextField = forwardRef<HTMLInputElement, Common & Omit<InputHTMLAttributes<HTMLInputElement>, "id">>(
  function TextField({ label, hint, error, required, className, ...input }, ref) {
    return (
      <Field label={label} hint={hint} error={error} required={required}>
        {(control) => <input ref={ref} className={cx("a-input", className)} type="text" {...control} {...input} />}
      </Field>
    );
  },
);

export interface NumberFieldProps extends Common, Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type" | "value" | "onChange"> {
  value: string;
  onValueChange: (text: string) => void;
  unit?: string;
}

/** Numeric text input that keeps what the person typed; parse with `parseNumber`. */
export const NumberField = forwardRef<HTMLInputElement, NumberFieldProps>(function NumberField(
  { label, hint, error, required, unit, value, onValueChange, className, ...input },
  ref,
) {
  return (
    <Field label={unit ? `${label} (${unit})` : label} hint={hint} error={error} required={required}>
      {(control) => (
        <input
          ref={ref}
          className={cx("a-input", className)}
          type="text"
          inputMode="decimal"
          value={value}
          onChange={(event) => onValueChange(event.target.value)}
          {...control}
          {...input}
        />
      )}
    </Field>
  );
});

export const DateField = forwardRef<HTMLInputElement, Common & Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type">>(
  function DateField({ label, hint, error, required, className, ...input }, ref) {
    return (
      <Field label={label} hint={hint} error={error} required={required}>
        {(control) => <input ref={ref} className={cx("a-input", className)} type="date" {...control} {...input} />}
      </Field>
    );
  },
);

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectFieldProps extends Common, Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  options: readonly SelectOption[];
  /** Label for an empty first option ("Any", "Not set"); omit when a value is required. */
  emptyLabel?: string;
}

export const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(function SelectField(
  { label, hint, error, required, options, emptyLabel, className, ...select },
  ref,
) {
  return (
    <Field label={label} hint={hint} error={error} required={required}>
      {(control) => (
        <select ref={ref} className={cx("a-input", className)} {...control} {...select}>
          {emptyLabel !== undefined ? <option value="">{emptyLabel}</option> : null}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
});

export const TextAreaField = forwardRef<HTMLTextAreaElement, Common & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id">>(
  function TextAreaField({ label, hint, error, required, className, ...area }, ref) {
    return (
      <Field label={label} hint={hint} error={error} required={required}>
        {(control) => <textarea ref={ref} className={cx("a-input", className)} {...control} {...area} />}
      </Field>
    );
  },
);

export function CheckboxField({ label, className, ...input }: { label: string } & Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  return (
    <label className={cx("a-checkbox", className)}>
      <input type="checkbox" {...input} />
      <span>{label}</span>
    </label>
  );
}

/** Parse a person's number text ("1,200", " 3.5 ") or return null with nothing typed. */
export function parseNumber(text: string): { ok: true; value: number | null } | { ok: false; message: string } {
  const trimmed = text.trim().replace(/,/g, "");
  if (!trimmed) return { ok: true, value: null };
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return { ok: false, message: "Enter a number, for example 12 or 3.5" };
  return { ok: true, value };
}
