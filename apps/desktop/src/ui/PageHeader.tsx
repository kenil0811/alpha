/** A 56px page header, aligned with the rail's and assistant's own 56px top rows. */
import type { ReactNode } from "react";
import "./PageHeader.css";

export function PageHeader({ title, right, center = false }: { title: ReactNode; right?: ReactNode; center?: boolean }) {
  return (
    <header className={center ? "page-header page-header--center" : "page-header"}>
      <h2 className="page-header__title">{title}</h2>
      {right ? <div className="page-header__right">{right}</div> : null}
    </header>
  );
}
