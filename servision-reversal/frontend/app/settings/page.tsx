"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Ribbon } from "@/components/Ribbon";

const EDITABLE: [string, string][] = [
  ["min_catalyst_move_pct", "Min catalyst move %"],
  ["min_volume_ratio", "Min volume ratio"],
  ["max_vwap_distance_pct", "Max VWAP distance %"],
  ["no_new_low_minutes", "No-new-low minutes"],
  ["stop_pct", "Stop %"],
  ["target1_pct", "Target 1 %"],
  ["target2_pct", "Target 2 %"],
  ["min_score_to_watch", "Score → watch"],
  ["min_score_to_qualify", "Score → qualify"],
];

export default function Settings() {
  const [versions, setVersions] = useState<any[]>([]);
  const [cfg, setCfg] = useState<Record<string, any>>({});
  const [label, setLabel] = useState("V2");
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.versions().then((d) => {
      setVersions(d.versions || []);
      if (d.versions?.[0]) setCfg(d.versions[0].config);
    }).catch((e) => setErr(e.message));
  }, []);

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
        Every threshold the strategy uses. Saving creates a new immutable strategy
        version so past observations stay tied to the rules that produced them.
      </p>
      <Ribbon text="Changing thresholds does not change history. Backtest a new version before trusting it." />

      {err && <div className="empty">Backend unreachable ({err}).</div>}

      <div className="section-title">Thresholds</div>
      <div className="panel">
        <div className="grid cols-3">
          {EDITABLE.map(([key, lbl]) => (
            <div className="field" key={key}>
              <label>{lbl}</label>
              <input
                type="number"
                value={cfg[key] ?? ""}
                onChange={(e) => setCfg({ ...cfg, [key]: +e.target.value })}
              />
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", marginTop: 18 }}>
          <div className="field" style={{ maxWidth: 160 }}>
            <label>New version label</label>
            <input value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          <button className="btn primary" onClick={save}>SAVE AS NEW VERSION</button>
          {saved && <span className="pos mono" style={{ fontSize: 12 }}>saved ✓</span>}
        </div>
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
                <td>{v.config.stop_pct}% / {v.config.target1_pct}% / {v.config.target2_pct}%</td>
                <td className="dim">{v.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
