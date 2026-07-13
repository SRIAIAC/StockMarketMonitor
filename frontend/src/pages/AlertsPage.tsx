import AlertFeed from "../components/AlertFeed";

export default function AlertsPage() {
  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">Rule engine + StockTwits</p>
        <h1>Alerts</h1>
      </header>
      <AlertFeed categories={["market", "news"]} title="Market Alerts" eyebrow="Rule engine · 1 per company per day" />
      <AlertFeed categories={["social"]} title="Social Media Alerts" eyebrow="StockTwits · trending posts" />
    </div>
  );
}
