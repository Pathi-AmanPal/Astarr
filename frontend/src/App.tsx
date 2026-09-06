import { Link, Route, Routes } from "react-router-dom";

import Shell from "./components/Shell";
import EntityList from "./pages/EntityList";
import EntityDetail from "./pages/EntityDetail";
import EvidenceView from "./pages/EvidenceView";

/** An unknown URL used to redirect silently to the ranking screen, which hides a
    mistyped or stale link rather than explaining it. */
function NoRoute() {
  return (
    <div className="state">
      <p className="state__title">No such screen</p>
      <p className="state__body">
        That address does not match any screen in this tool. The ranking is the
        entry point — every entity and every finding is reachable from it.
      </p>
      <div className="state__actions">
        <Link className="btn btn--primary" to="/">
          Go to the ranking
        </Link>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<EntityList />} />
        <Route path="/entities/:id" element={<EntityDetail />} />
        <Route path="/findings/:id" element={<EvidenceView />} />
        <Route path="*" element={<NoRoute />} />
      </Routes>
    </Shell>
  );
}
