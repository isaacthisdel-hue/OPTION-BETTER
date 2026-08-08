"use client";
import { useEffect, useState } from "react";
import { api, Candidate } from "@/lib/api";
import { CandidateCard } from "@/components/Candidate";
import { Ribbon } from "@/components/Ribbon";

export default function Scanner() {
  const [cands, setCands] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [lastScan, setLastScan] = useState<string | null>(null);

  async function load() {
    try {
      const d = await api.candidates();
      setCands(d.candidates || []);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function scan() {
    setLoading(true);
    setErr(null);
    try {
      const d = await api.scan();
      setCands(d.candidates || []);
      setLastScan(new Date().toLocaleTimeString());
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
        <button className="btn primary" onClick={scan} disabled={loading}>
          {loading ? "SCANNING…" : "RUN SCAN"}
        </button>
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

      {!err && cands.length === 0 && (
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
