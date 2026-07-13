import EconomicCalendarPanel from "../components/EconomicCalendarPanel";

export default function EconomicCalendarPage() {
  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">India macro calendar</p>
        <h1>Economic Calendar</h1>
      </header>
      <EconomicCalendarPanel limit={50} />
    </div>
  );
}
