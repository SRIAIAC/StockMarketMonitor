import AIRecommendationCard from "../components/AIRecommendationCard";
import BuySellPanel from "../components/BuySellPanel";
import FiiDiiPanel from "../components/FiiDiiPanel";

export default function RecommendationsPage() {
  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">Watchlist agent-scored + market-wide web signals</p>
        <h1>AI Recommendations</h1>
      </header>
      <AIRecommendationCard limit={15} />
      <BuySellPanel />
      <FiiDiiPanel />
    </div>
  );
}
