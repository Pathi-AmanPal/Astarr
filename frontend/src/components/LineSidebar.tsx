/** Primary navigation.
 *
 *  A line sidebar rather than a tab bar: the destinations are places you stay in,
 *  not modes you flick between, and a supervisor moving between the overview and a
 *  case wants the other destinations still visible while they do it.
 *
 *  Two things it must get right, and both are easy to get wrong:
 *
 *  **The active item is derived from the URL, never from click state.** Landing on
 *  /entities/CSE-013 from a bookmark, or arriving there by browser-back, has to light
 *  the same item as clicking Entities did. Anything held in component state gets this
 *  wrong the moment navigation happens by any route other than a click.
 *
 *  **Every item is a real link.** They are <Link> elements, so Enter works because
 *  they are anchors and not because of a key handler, middle-click and
 *  open-in-new-tab work, and a screen reader announces them as links with a current
 *  page. A <div onClick> with role="link" and a keydown handler reimplements a
 *  fraction of that, badly.
 */

import { NavLink, useLocation } from "react-router-dom";

interface Destination {
  to: string;
  label: string;
  hint: string;
  /** Owns any URL under this prefix, so a detail page keeps its section lit. */
  prefix?: string;
}

const DESTINATIONS: Destination[] = [
  { to: "/", label: "Overview", hint: "How the population is performing" },
  { to: "/entities", label: "Entities", hint: "Ranked schedule", prefix: "/entities" },
  { to: "/data", label: "Data", hint: "What is loaded, and provenance", prefix: "/data" },
];

export default function LineSidebar() {
  const { pathname } = useLocation();

  return (
    <nav className="rail" aria-label="Primary">
      <ul className="rail__list">
        {DESTINATIONS.map((d) => {
          // `end` on NavLink handles "/" alone; a prefix match handles the detail
          // routes underneath a section.
          const active = d.prefix
            ? pathname === d.prefix || pathname.startsWith(`${d.prefix}/`)
            : pathname === d.to;
          return (
            <li key={d.to}>
              <NavLink
                to={d.to}
                end={!d.prefix}
                className={`rail__item${active ? " is-active" : ""}`}
                aria-current={active ? "page" : undefined}
              >
                {/* The line the component is named for. It is the active indicator,
                    so it must not be the only one -- weight and ink change too. */}
                <span className="rail__line" aria-hidden="true" />
                <span className="rail__text">
                  <span className="rail__label">{d.label}</span>
                  <span className="rail__hint">{d.hint}</span>
                </span>
              </NavLink>
            </li>
          );
        })}
      </ul>

      {/* Named as absent rather than omitted. A destination that is coming is worth
          one line; a nav item that leads to a placeholder screen is not. */}
      <p className="rail__note">
        Cases — the finding tree — lands in the next phase. Findings are reachable
        today from any entity.
      </p>
    </nav>
  );
}
