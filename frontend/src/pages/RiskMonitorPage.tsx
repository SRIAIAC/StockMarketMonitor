import RiskMonitor from "../components/RiskMonitor";

export default function RiskMonitorPage() {
  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">Volatility & liquidity</p>
        <h1>Risk Monitor</h1>
      </header>
      <RiskMonitor />
    </div>
  );
}
