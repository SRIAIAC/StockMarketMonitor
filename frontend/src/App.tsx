import { useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Analytics from "./pages/Analytics";
import Calculators from "./pages/Calculators";
import AgentsStatusPage from "./pages/AgentsStatusPage";
import LiveMarketPage from "./pages/LiveMarketPage";
import NewsPage from "./pages/NewsPage";
import SocialPage from "./pages/SocialPage";
import CorporateActionsPage from "./pages/CorporateActionsPage";
import SebiFilingsPage from "./pages/SebiFilingsPage";
import EconomicCalendarPage from "./pages/EconomicCalendarPage";
import SectorRotationPage from "./pages/SectorRotationPage";
import RiskMonitorPage from "./pages/RiskMonitorPage";
import RecommendationsPage from "./pages/RecommendationsPage";
import WatchlistPage from "./pages/WatchlistPage";
import AlertsPage from "./pages/AlertsPage";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import ChatBot from "./components/ChatBot";
import TickerStrip from "./components/TickerStrip";
import "./App.css";

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <BrowserRouter>
      <div className={"app-shell" + (sidebarOpen ? " app-shell-sidebar-open" : "")}>
        <TopBar onToggleSidebar={() => setSidebarOpen((v) => !v)} />
        <div className="app-body">
          <Sidebar collapsed={!sidebarOpen} onNavigate={() => setSidebarOpen(false)} />
          {sidebarOpen && <div className="sidebar-scrim" onClick={() => setSidebarOpen(false)} />}
          <main className="app-main">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/agents" element={<AgentsStatusPage />} />
              <Route path="/live-market" element={<LiveMarketPage />} />
              <Route path="/news" element={<NewsPage />} />
              <Route path="/social" element={<SocialPage />} />
              <Route path="/corporate-actions" element={<CorporateActionsPage />} />
              <Route path="/sebi-filings" element={<SebiFilingsPage />} />
              <Route path="/economic-calendar" element={<EconomicCalendarPage />} />
              <Route path="/sector-rotation" element={<SectorRotationPage />} />
              <Route path="/risk-monitor" element={<RiskMonitorPage />} />
              <Route path="/recommendations" element={<RecommendationsPage />} />
              <Route path="/watchlist" element={<WatchlistPage />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/calculators" element={<Calculators />} />
            </Routes>
          </main>
        </div>
        <TickerStrip />
      </div>
      <ChatBot />
    </BrowserRouter>
  );
}

export default App;
