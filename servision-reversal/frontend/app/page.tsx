"use client";
import { useEffect, useState } from "react";
import { api, Candidate } from "@/lib/api";
import { CandidateCard } from "@/components/Candidate";
import { Ribbon } from "@/components/Ribbon";

type MarketStatus = { open: boolean; reason: string; now_et: string };

export default function Scanner() {
  const [cands, setCands] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [lastScan, setLastScan] = useState<string | null>(null);
  const [market, setMarket] = useState<MarketStatus | null>(null);
  const [closedNotice, setClosedNotice] = useState<MarketStatus | null>(null);

  async function load() {
    try {
      const d = await api.candidates();
      setCands(d.candidates || []);
    } catch (e: any) {
      setErr(e.message);
    }
    try {
      setMarket(await api.marketStatus());
    } catch {
      /* non-fatal */
    }
  }

  async function scan(force = false) {
    setLoading(true);
    setErr(null);
    setClosedNotice(null);
    try {
      const d = await api.scan(force);
      if (d.market_open === false && !force) {
        setClosedNotice(d.market_status);
        setCands([]);
      } else {
        setCands(d.candidates || []);
        setLastScan(new Date().toLocaleTimeString());
      }
      if (d.market_status) setMarket(d.market_status);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const qualified = cands.filter((c) => c.status === "QUALIFIED");
  const watch = cands.filter((c) => c.status === "WATCH");

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="eyebrow">Live scanner</div>
          <h1>Reversal candidates</h1>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {market && (
            <span className={`sessiondot ${market.open ? "open" : "closed"}`} title={market.reason}>
              <span className="dot" /> {market.open ? "MARKET OPEN" : "MARKET CLOSED"}
            </span>
          )}
          <button className="btn primary" onClick={() => scan(false)} disabled={loading}>
            {loading ? "SCANNING…" : "RUN SCAN"}
          </button>
        </div>
      </div>
      <p className="pagesub">
        Scores the universe against your configured reversal criteria. Each score is
        the sum of visible components — nothing hidden. {lastScan && `Last scan ${lastScan}.`}
      </p>

      <Ribbon />

      {err && (
        <div className="empty">
          Couldn&apos;t reach the backend ({err}). Check that the API is running and
          NEXT_PUBLIC_API_BASE is set to {api.base}.
        </div>
      )}

      {closedNotice && (
        <div className="notice closed">
          <div className="notice-head">
            <span className="mono">MARKET CLOSED</span>
            <span className="dim">{closedNotice.now_et}</span>
          </div>
          <p>
            {closedNotice.reason} Live scanning needs intraday data, so there&apos;s
            nothing to score right now. The scanner runs during regular US hours
            (09:30–16:00 ET, weekdays).
          </p>
          <button className="btn" onClick={() => scan(true)} disabled={loading}>
            SCAN ANYWAY (test a watchlist)
          </button>
        </div>
      )}

      {!err && !closedNotice && cands.length === 0 && (
        <div className="empty">
          No candidates yet. Run a scan — on the free tier the universe is your
          watchlist or today&apos;s earnings names.
        </div>
      )}

      {qualified.length > 0 && (
        <>
          <div className="section-title">Qualified · {qualified.length}</div>
          <div className="grid cols-2">
            {qualified.map((c) => (
              <CandidateCard key={c.symbol} c={c} />
            ))}
          </div>
        </>
      )}

      {watch.length > 0 && (
        <>
          <div className="section-title">Watch · {watch.length}</div>
          <div className="grid cols-2">
            {watch.map((c) => (
              <CandidateCard key={c.symbol} c={c} />
            ))}
          </div>
        </>
      )}
    </>
  );
}
