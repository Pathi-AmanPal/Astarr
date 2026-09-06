import { Link, Route, Routes } from "react-router-dom";

import Shell from "./components/Shell";
import DataPage from "./pages/DataPage";
import EntityList from "./pages/EntityList";
import EntityDetail from "./pages/EntityDetail";
import EvidenceView from "./pages/EvidenceView";
import OverviewPage from "./pages/OverviewPage";

/** An unknown URL used to redirect silently to the ranking screen, which hides a
    mistyped or stale link rather than explaining it. */
function NoRoute() {
  return (
    <div className="state">
      <p className="state__title">No such screen</p>
      <p className="state__body">
        That address does not match any screen in this tool. The overview is the
        entry point — every entity and every finding is reachable from it.
      </p>
      <div className="state__actions">
        <Link className="btn btn--primary" to="/">
          Go to the overview
        </Link>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/entities" element={<EntityList />} />
        <Route path="/entities/:id" element={<EntityDetail />} />
        {/* Findings live under Entities in the trail even though the URL is flat:
            a finding is always reached from the entity that owns it. */}
        <Route path="/findings/:id" element={<EvidenceView />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="*" element={<NoRoute />} />
      </Routes>
    </Shell>
  );
}
