import { useState } from "react";
import { api } from "../api/client";

export default function RefreshButton() {
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      await api.refreshAnalytics();
    } catch (e) {
      console.error("Refresh failed", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button className="refresh-btn" onClick={handleClick} disabled={loading} aria-label="Refresh data">
      {loading ? "Refreshing…" : "Refresh"}
    </button>
  );
}
