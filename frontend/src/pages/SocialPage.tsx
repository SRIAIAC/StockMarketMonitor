import SocialSentimentGauge from "../components/SocialSentimentGauge";
import SentimentHeatmap from "../components/SentimentHeatmap";
import YouTubeSentiment from "../components/YouTubeSentiment";

export default function SocialPage() {
  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">StockTwits · YouTube</p>
        <h1>Social Sentiment</h1>
      </header>
      <SocialSentimentGauge />
      <SentimentHeatmap />
      <YouTubeSentiment />
    </div>
  );
}
