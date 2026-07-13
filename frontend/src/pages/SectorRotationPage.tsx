import SectorPerformance from "../components/SectorPerformance";

export default function SectorRotationPage() {
  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">India breadth · NSE sectoral indices</p>
        <h1>Sector Rotation</h1>
      </header>
      <SectorPerformance compact={false} />
    </div>
  );
}
