import NewsPanel from "../components/NewsPanel";

export default function NewsPage() {
  return (
    <div className="dashboard">
      <header className="page-header">
        <p className="eyebrow">Google News RSS · VADER scored</p>
        <h1>News Intelligence</h1>
      </header>
      <NewsPanel />
    </div>
  );
}
