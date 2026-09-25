import { useId, type ReactNode } from "react";

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export { cx };

export interface PageProps {
  /** The App's name or the task the person is doing, in their words. */
  title: string;
  description?: ReactNode;
  /** Primary page actions (one primary button at most). */
  actions?: ReactNode;
  /** Connection or attention banner shown under the header. */
  status?: ReactNode;
  children: ReactNode;
}

/** Page frame: one h1, optional description and actions, then the content in a main landmark. */
export function Page({ title, description, actions, status, children }: PageProps) {
  return (
    <main className="a-page">
      <header className="a-page__header">
        <div>
          <h1 className="a-page__title">{title}</h1>
          {description ? <p className="a-page__description">{description}</p> : null}
        </div>
        {actions ? <div className="a-page__actions">{actions}</div> : null}
      </header>
      {status}
      {children}
    </main>
  );
}

export interface SectionProps {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}

/** A titled region (h2). Screen readers can jump between sections by their titles. */
export function Section({ title, description, actions, children }: SectionProps) {
  const id = useId();
  return (
    <section className="a-section" aria-labelledby={id}>
      <div className="a-section__header">
        <h2 className="a-section__title" id={id}>
          {title}
        </h2>
        {actions ? <div className="a-cluster">{actions}</div> : null}
      </div>
      {description ? <p className="a-section__description">{description}</p> : null}
      {children}
    </section>
  );
}

export function Stack({ children, tight = false }: { children: ReactNode; tight?: boolean }) {
  return <div className={cx("a-stack", tight && "a-stack--tight")}>{children}</div>;
}

export function Cluster({ children }: { children: ReactNode }) {
  return <div className="a-cluster">{children}</div>;
}

/** Responsive columns: side by side when there is room, stacked on narrow windows. */
export function Columns({ children }: { children: ReactNode }) {
  return <div className="a-columns">{children}</div>;
}

export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className="a-visually-hidden">{children}</span>;
}
