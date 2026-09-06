/** The trail back. Every screen has one, so no screen is a dead end. */

import { Link } from "react-router-dom";

export interface Crumb {
  label: string;
  to?: string;
}

export default function Crumbs({ trail }: { trail: Crumb[] }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      {trail.map((c, i) => (
        <span key={`${c.label}-${i}`}>
          {i > 0 && (
            <span className="crumbs__sep" aria-hidden="true">
              {"  /  "}
            </span>
          )}
          {c.to ? (
            <Link to={c.to}>{c.label}</Link>
          ) : (
            <span className="crumbs__here" aria-current="page">
              {c.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
