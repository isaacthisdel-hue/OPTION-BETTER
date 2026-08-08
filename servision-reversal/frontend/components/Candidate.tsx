import type { Candidate } from "@/lib/api";

function Ledger({ components }: { components: Candidate["components"] }) {
  const maxAbs = Math.max(1, ...components.map((c) => Math.abs(c.points)));
  return (
    <div className="ledger">
      {components.map((c, i) => {
        const pct = (Math.abs(c.points) / maxAbs) * 48; // half-width max
        const pos = c.points >= 0;
        return (
          <div className="row" key={i} title={c.reason}>
            <div>
              <div className="name">{c.name.replace(/_/g, " ")}</div>
              <div className="reason">{c.reason}</div>
            </div>
            <div className="track">
              <div className="axis" />
              <div
                className={`fill ${pos ? "pos" : "neg"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className={`pts ${pos ? "pos" : "neg"}`}>
              {pos ? "+" : ""}
              {c.points.toFixed(1)}
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

export function CandidateCard({ c }: { c: Candidate }) {
  return (
    <div className="candcard">
      <div className="top">
        <div>
          <div className="sym">{c.symbol}</div>
          <div className="cat">{c.catalyst || "no catalyst"}</div>
          <div className={`statusbadge ${c.status}`}>
            {c.status === "QUALIFIED" ? "QUALIFIED PAPER SETUP" : c.status}
          </div>
        </div>
        <div>
          <div className="scorebig">
            {c.total.toFixed(0)}
            <span className="max"> /100</span>
          </div>
        </div>
      </div>

      <div className="metrics">
        <div className="m">
          <div className="k">Move</div>
          <div className={`v ${(c.move_pct ?? 0) < 0 ? "neg" : "pos"}`}>
            {c.move_pct != null ? `${c.move_pct.toFixed(1)}%` : "—"}
          </div>
        </div>
        <div className="m">
          <div className="k">Volume</div>
          <div className="v">{c.volume_ratio != null ? `${c.volume_ratio.toFixed(1)}x` : "—"}</div>
        </div>
        <div className="m">
          <div className="k">VWAP</div>
          <div className={`v ${(c.vwap_distance_pct ?? 0) < 0 ? "neg" : "pos"}`}>
            {c.vwap_distance_pct != null ? `${c.vwap_distance_pct.toFixed(1)}%` : "—"}
          </div>
        </div>
        <div className="m">
          <div className="k">Higher low</div>
          <div className="v">{confChip(c.higher_low)}</div>
        </div>
        <div className="m">
          <div className="k">VWAP reclaim</div>
          <div className="v">{confChip(c.vwap_reclaim)}</div>
        </div>
        <div className="m">
          <div className="k">Price</div>
          <div className="v">{c.price != null ? `$${c.price.toFixed(2)}` : "—"}</div>
        </div>
      </div>

      <Ledger components={c.components} />
    </div>
  );
}
