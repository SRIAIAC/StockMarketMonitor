import MarketBriefingPanel from "../components/MarketBriefingPanel";
import AgentStatusRow from "../components/AgentStatusRow";
import MarketOverviewChart from "../components/MarketOverviewChart";
import NewsPanel from "../components/NewsPanel";
import SocialSentimentGauge from "../components/SocialSentimentGauge";
import AIRecommendationCard from "../components/AIRecommendationCard";
import SectorPerformance from "../components/SectorPerformance";
import RiskMonitor from "../components/RiskMonitor";
import CorporateActionsPanel from "../components/CorporateActionsPanel";
import EconomicCalendarPanel from "../components/EconomicCalendarPanel";

export default function Dashboard() {
  return (
    <div className="dashboard overview-page">
      <MarketBriefingPanel />
      <AgentStatusRow />

      <div className="overview-grid overview-grid-top">
        <MarketOverviewChart />
        <NewsPanel compact limit={8} />
        <SocialSentimentGauge />
      </div>

      <AIRecommendationCard limit={5} />

      <div className="overview-grid overview-grid-bottom">
        <SectorPerformance compact />
        <RiskMonitor />
        <CorporateActionsPanel limit={6} />
        <EconomicCalendarPanel limit={6} />
      </div>
    </div>
  );
}
