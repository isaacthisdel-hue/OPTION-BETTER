"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Ribbon } from "@/components/Ribbon";

// Plain-language settings, grouped, each with a hover definition (*).
type Field = { key: string; label: string; def: string; suffix?: string };
type Group = { title: string; blurb: string; fields: Field[] };

const GROUPS: Group[] = [
  {
    title: "Entry criteria",
    blurb: "What makes a stock show up as a candidate in the first place.",
    fields: [
      {
        key: "min_catalyst_move_pct",
        label: "Minimum drop to qualify",
        suffix: "%",
        def: "How far a stock must have fallen from yesterday's close (a negative number) before the scanner considers it. A bigger drop means a bigger potential overreaction to bounce from. Default −7 means it must be down at least 7%.",
      },
      {
        key: "min_volume_ratio",
        label: "Minimum volume surge",
        suffix: "×",
        def: "Today's trading volume divided by its normal average. 2.0 means it must be trading at twice its usual volume — proof the move is real and widely traded, not thin noise.",
      },
      {
        key: "max_vwap_distance_pct",
        label: "Max stretch below VWAP",
        suffix: "%",
        def: "VWAP is the day's volume-weighted average price — a fair-value line. This is the furthest BELOW that line a stock can be and still count. Too far below and it may be in free-fall rather than setting up to revert.",
      },
    ],
  },
  {
    title: "Confirmation",
    blurb: "Signs the drop has stalled and a bounce may be starting.",
    fields: [
      {
        key: "no_new_low_minutes",
        label: "Minutes without a new low",
        suffix: "min",
        def: "The stock must go this many minutes without printing a fresh intraday low — a sign the selling pressure has paused. Default 15 minutes.",
      },
    ],
  },
  {
    title: "Risk & targets",
    blurb: "Sizing for the stop and profit targets.",
    fields: [
      {
        key: "stop_pct",
        label: "Stop-loss",
        suffix: "%",
        def: "How far below the entry price the simulated trade is closed for a loss. Smaller = tighter risk but stopped out more often. Default 1.5%.",
      },
      {
        key: "target1_pct",
        label: "First target",
        suffix: "%",
        def: "The first profit target above entry where the simulated trade takes gains. Default 1.5%.",
      },
      {
        key: "target2_pct",
        label: "Second target",
        suffix: "%",
        def: "A further profit target above entry for a bigger move. Default 3%.",
      },
    ],
  },
  {
    title: "Score gates",
    blurb: "How the total points turn into a verdict.",
    fields: [
      {
        key: "min_score_to_watch",
        label: "Score to reach WATCH",
        suffix: "pts",
        def: "Total points a stock needs to appear on the WATCH list. Below this it is skipped entirely. Default 60.",
      },
      {
        key: "min_score_to_qualify",
        label: "Score to reach QUALIFIED",
        suffix: "pts",
        def: "Total points needed to become a full QUALIFIED setup (and record a trade). This is the strict bar. Default 80.",
      },
    ],
  },
];

function Info({ text }: { text: string }) {
  return (
    <span className="info" tabIndex={0}>
      <span className="info-mark">*</span>
      <span className="info-pop">{text}</span>
    </span>
  );
}

export default function Settings() {
  const [versions, setVersions] = useState<any[]>([]);
  const [cfg, setCfg] = useState<Record<string, any>>({});
  const [label, setLabel] = useState("V2");
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [btBusy, setBtBusy] = useState<number | null>(null);

  async function loadVersions() {
    try {
      const d = await api.versions();
      setVersions(d.versions || []);
      setActiveId(d.active_id ?? null);
      setCfg((prev) => (Object.keys(prev).length ? prev : d.versions?.[0]?.config || {}));
    } catch (e: any) {
      setErr(e.message);
    }
  }
  useEffect(() => { loadVersions(); }, []);

  async function activate(id: number) {
    try { await api.activateVersion(id); loadVersions(); } catch (e: any) { setErr(e.message); }
  }
  async function backtestVersion(id: number) {
    setBtBusy(id); setErr(null);
    try {
      const d = await api.backtestVersion(id);
      if (d.available === false) setErr(d.error || "Backtest failed.");
      await loadVersions();
    } catch (e: any) { setErr(e.message); } finally { setBtBusy(null); }
  }
  async function removeVersion(id: number) {
    try {
      const d = await api.deleteVersion(id);
      if (!d.ok) setErr(d.error || "Could not delete.");
      else { setErr(null); loadVersions(); }
    } catch (e: any) { setErr(e.message); }
  }

  async function save() {
    setSaved(false);
    try {
      await fetch(`${api.base}/api/strategy-versions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, config: cfg, notes: "edited in UI" }),
      });
      const d = await api.versions();
      setVersions(d.versions || []);
      setSaved(true);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="eyebrow">Strategy configuration</div>
          <h1>Settings</h1>
        </div>
      </div>
      <p className="pagesub">
        These are the dials that define the strategy. Hover the{" "}
        <span className="info-mark" style={{ position: "static" }}>
          *
        </span>{" "}
        beside any setting for a plain-English explanation. Saving creates a new{" "}
        <b>version</b> so past results stay tied to the exact rules that produced them.
      </p>
      <Ribbon text="Changing these does not rewrite history. Always backtest a new version before trusting it." />

      {err && <div className="empty">Backend unreachable ({err}).</div>}

      {GROUPS.map((g) => (
        <div key={g.title}>
          <div className="section-title">{g.title}</div>
          <p className="dim" style={{ fontSize: 12, margin: "-4px 0 12px" }}>{g.blurb}</p>
          <div className="panel">
            <div className="grid cols-3">
              {g.fields.map((f) => (
                <div className="field" key={f.key}>
                  <label>
                    {f.label}
                    <Info text={f.def} />
                  </label>
                  <div className="inputwrap">
                    <input
                      type="number"
                      value={cfg[f.key] ?? ""}
                      onChange={(e) => setCfg({ ...cfg, [f.key]: +e.target.value })}
                    />
                    {f.suffix && <span className="suffix">{f.suffix}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ))}

      <div className="panel" style={{ marginTop: 20, display: "flex", gap: 10, alignItems: "flex-end" }}>
        <div className="field" style={{ maxWidth: 180 }}>
          <label>
            New version label
            <Info text="A name for this set of rules, like V2 or 'tighter-stops'. Saving snapshots the current dials under this label — you can backtest and compare versions without overwriting the old one." />
          </label>
          <input value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <button className="btn primary" onClick={save}>
          SAVE AS NEW VERSION
        </button>
        {saved && (
          <span className="pos mono" style={{ fontSize: 12 }}>
            saved ✓
          </span>
        )}
      </div>

      <div className="section-title">Version history</div>
      <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
        <table className="data">
          <thead>
            <tr>
              <th>ID</th>
              <th>Label</th>
              <th>Qualify gate</th>
              <th>Stop / T1 / T2</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.id}>
                <td>{v.id}</td>
                <td style={{ fontWeight: 600 }}>{v.label}</td>
                <td>{v.config.min_score_to_qualify}</td>
                <td>
                  {v.config.stop_pct}% / {v.config.target1_pct}% / {v.config.target2_pct}%
                </td>
                <td className="dim">{v.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
