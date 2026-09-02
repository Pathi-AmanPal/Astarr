import { Navigate, Route, Routes } from "react-router-dom";

import EntityList from "./pages/EntityList";
import EntityDetail from "./pages/EntityDetail";
import EvidenceView from "./pages/EvidenceView";

export default function App() {
  return (
    <div className="page">
      <Routes>
        <Route path="/" element={<EntityList />} />
        <Route path="/entities/:id" element={<EntityDetail />} />
        <Route path="/findings/:id" element={<EvidenceView />} />
        {/* Any unknown URL returns to the list rather than rendering blank. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
