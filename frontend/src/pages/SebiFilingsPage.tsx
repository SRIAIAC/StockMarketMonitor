import RegulatoryAnnouncementsPanel from "../components/RegulatoryAnnouncementsPanel";

export default function SebiFilingsPage() {
  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">NSE regulatory announcements · not SEBI EDIFAR</p>
        <h1>SEBI Filings</h1>
      </header>
      <p className="page-header-note">
        No free public API exists for SEBI's own filing system. This feed is NSE's own
        regulatory/compliance disclosure feed (board meetings, credit ratings, LODR
        compliance, etc.) for NSE-listed companies — the closest free, real substitute.
      </p>
      <RegulatoryAnnouncementsPanel limit={100} />
    </div>
  );
}
