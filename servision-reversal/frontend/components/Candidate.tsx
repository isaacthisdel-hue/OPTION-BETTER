"use client";
import { useState } from "react";
import { api, type Candidate } from "@/lib/api";

function Ledger({ components }: { components: Candidate["components"] }) {
  const maxAbs = Math.max(1, ...components.map((c) => Math.abs(c.points)));
  return (
    <div className="ledger">
      {components.map((c, i) => {
        const pct = (Math.abs(c.points) / maxAbs) * 48;
        const pos = c.points >= 0;
        return (
          <div className="row" key={i} title={c.reason}>
            <div>
              <div className="name">{c.name.replace(/_/g, " ")}</div>
              <div className="reason">{c.reason}</div>
            </div>
            <div className="track">
              <div className="axis" />
              <div className={`fill ${pos ? "pos" : "neg"}`} style={{ width: `${pct}%` }} />
            </div>
            <div className={`pts ${pos ? "pos" : "neg"}`}>
              {pos ? "+" : ""}{c.points.toFixed(1)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function confChip(v?: boolean, pendingLabel = "PENDING") {
  if (v === true) return <span className="chip ok">CONFIRMED</span>;
  if (v === false) return <span className="chip pending">{pendingLabel}</span>;
  return <span className="chip no">—</span>;
}

function Spark({ data }: { data?: number[] }) {
  if (!data || data.length < 2) return <div className="spark-empty faint">no intraday</div>;
  const w = 160, h = 40;
  const min = Math.min(...data), max = Math.max(...data), rng = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / rng) * h}`).join(" ");
  const up = data[data.length - 1] >= data[0];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="spark">
      <polyline points={pts} fill="none" stroke={up ? "var(--cyan)" : "var(--coral)"} strokeWidth="1.5" />
    </svg>
  );
}

export function CandidateCard({ c }: { c: Candidate }) {
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await api.saveIdea({
        symbol: c.symbol, entry_price: c.price, score: c.total,
        estimated_reversal_pct: c.estimated_reversal_pct,
        expiry: c.option_aim?.expiry_next_friday,
      });
      setSaved(true);
    } catch {
      /* noop */
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="candcard">
      <div className="top">
        <div>
          <div className="sym">{c.symbol}</div>
          <div className="cat">{c.catalyst || "no catalyst"}</div>
          <div className={`statusbadge ${c.status}`}>{c.status}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="scorebig">{c.total.toFixed(0)}<span className="max"> /100</span></div>
          <button className={`savebtn ${saved ? "on" : ""}`} onClick={save} disabled={busy || saved} title="Save to track">
            {saved ? "★ Saved" : "☆ Save"}
          </button>
        </div>
      </div>

      <div className="revstrip">
        <div className="revnum">
          <div className="k">Est. reversal</div>
          <div className="v pos">{c.estimated_reversal_pct != null ? `+${c.estimated_reversal_pct.toFixed(1)}%` : "—"}</div>
        </div>
        <div className="revaim">
          {c.option_aim && (
            <div className="mono cyan">{c.option_aim.direction} · exp {c.option_aim.expiry_next_friday}</div>
          )}
          <div className="faint" style={{ fontSize: 11 }}>
            {c.reversal_tier || ""}{c.reversal_confidence ? ` · ${c.reversal_confidence}` : ""}
          </div>
        </div>
        <Spark data={c.spark} />
      </div>

      <div className="metrics">
        <div className="m"><div className="k">Move</div><div className={`v ${(c.move_pct ?? 0) < 0 ? "neg" : "pos"}`}>{c.move_pct != null ? `${c.move_pct.toFixed(1)}%` : "—"}</div></div>
        <div className="m"><div className="k">Volume</div><div className="v">{c.volume_ratio != null ? `${c.volume_ratio.toFixed(1)}x` : "—"}</div></div>
        <div className="m"><div className="k">VWAP</div><div className={`v ${(c.vwap_distance_pct ?? 0) < 0 ? "neg" : "pos"}`}>{c.vwap_distance_pct != null ? `${c.vwap_distance_pct.toFixed(1)}%` : "—"}</div></div>
        <div className="m"><div className="k">Higher low</div><div className="v">{confChip(c.higher_low)}</div></div>
        <div className="m"><div className="k">VWAP reclaim</div><div className="v">{confChip(c.vwap_reclaim)}</div></div>
        <div className="m"><div className="k">Price</div><div className="v">{c.price != null ? `$${c.price.toFixed(2)}` : "—"}</div></div>
      </div>

      <Ledger components={c.components} />
    </div>
  );
}
