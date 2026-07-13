import CorporateActionsPanel from "../components/CorporateActionsPanel";

export default function CorporateActionsPage() {
  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">NSE · whole market</p>
        <h1>Corporate Actions</h1>
      </header>
      <CorporateActionsPanel limit={100} />
    </div>
  );
}
