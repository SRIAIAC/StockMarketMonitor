from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 100 NSE tickers spanning large/mid/small cap across banking, IT, FMCG,
    # auto, pharma, energy, cement, metals, chemicals, consumer, and more —
    # see agents/README.md for the cap/sector breakdown. TMPV = Tata Motors
    # Passenger Vehicles (incl. JLR) — TATAMOTORS.NS was delisted under that
    # symbol after the Oct 2025 commercial/passenger-vehicle demerger. Every
    # ticker below (including the 50 added to double the original watchlist)
    # was verified live via yfinance before being added — see EXPERIMENTS.md.
    watchlist: str = (
        "RELIANCE.NS,HDFCBANK.NS,TCS.NS,ICICIBANK.NS,BHARTIARTL.NS,INFY.NS,HINDUNILVR.NS,"
        "ITC.NS,LT.NS,SBIN.NS,AXISBANK.NS,KOTAKBANK.NS,MARUTI.NS,SUNPHARMA.NS,TMPV.NS,"
        "TATASTEEL.NS,NTPC.NS,POWERGRID.NS,ULTRACEMCO.NS,ASIANPAINT.NS,"
        "WIPRO.NS,HCLTECH.NS,BAJFINANCE.NS,BAJAJFINSV.NS,TITAN.NS,NESTLEIND.NS,ADANIENT.NS,"
        "ADANIPORTS.NS,JSWSTEEL.NS,HINDALCO.NS,ONGC.NS,COALINDIA.NS,BPCL.NS,GRASIM.NS,"
        "DRREDDY.NS,CIPLA.NS,HEROMOTOCO.NS,EICHERMOT.NS,INDUSINDBK.NS,M&M.NS,"
        "CGPOWER.NS,DIXON.NS,COFORGE.NS,PERSISTENT.NS,MPHASIS.NS,CDSL.NS,IEX.NS,CYIENT.NS,"
        "GLENMARK.NS,BIRLACORPN.NS,FEDERALBNK.NS,AUBANK.NS,PIIND.NS,DEEPAKNTR.NS,SRF.NS,"
        "GODREJCP.NS,DABUR.NS,MARICO.NS,BERGEPAINT.NS,HAVELLS.NS,AMBUJACEM.NS,TORNTPHARM.NS,"
        "LUPIN.NS,ESCORTS.NS,BANKBARODA.NS,PNB.NS,IDFCFIRSTB.NS,ZYDUSLIFE.NS,ALKEM.NS,JUBLFOOD.NS,"
        "TRENT.NS,PAGEIND.NS,VOLTAS.NS,INDHOTEL.NS,LTTS.NS,"
        "CAMS.NS,KPITTECH.NS,RAINBOW.NS,CLEAN.NS,ANGELONE.NS,ROUTE.NS,LATENTVIEW.NS,"
        "HAPPSTMNDS.NS,GRANULES.NS,RATNAMANI.NS,"
        "POLYCAB.NS,KEI.NS,BLUESTARCO.NS,APLAPOLLO.NS,JBCHEPHARM.NS,NAVINFLUOR.NS,FINEORG.NS,"
        "GALAXYSURF.NS,CENTURYPLY.NS,VGUARD.NS,RADICO.NS,METROPOLIS.NS,LALPATHLAB.NS,"
        "CROMPTON.NS,IRCTC.NS"
    )

    anthropic_api_key: str = ""
    newsapi_key: str = ""

    # Local Ollama — the MAS chat assistant's no-API-key path. Tried whenever
    # ANTHROPIC_API_KEY is unset (or the Claude call fails), before falling
    # further back to the keyword-based reply. `ollama serve` must be running
    # locally with `ollama_model` pulled; if it isn't reachable, the chat
    # endpoint just falls through to the keyword fallback — same
    # never-raise-let-the-caller-degrade contract as claude_client.py.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    price_poll_minutes: int = 15
    news_poll_minutes: int = 60
    social_poll_minutes: int = 60

    database_url: str = "sqlite:///./market_monitor.db"

    # Comma-separated list of allowed CORS origins. Defaults to local dev
    # only — a real deployment (e.g. Cloud Run) must set this to the
    # frontend's actual public URL(s), since the frontend and backend get
    # separate hostnames there (not just separate ports on localhost).
    # Includes 5174/5175 too since Vite silently falls back to the next free
    # port when 5173 is already taken (e.g. another dev instance running).
    allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5175,http://127.0.0.1:5175,"
        "http://localhost:5190,http://127.0.0.1:5190"
    )

    @property
    def tickers(self) -> list[str]:
        return [t.strip().upper() for t in self.watchlist.split(",") if t.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
