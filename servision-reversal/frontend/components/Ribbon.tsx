export function Ribbon({ text }: { text?: string }) {
  return (
    <div className="ribbon">
      <span className="mono">RESEARCH ONLY</span>
      <span>
        {text ||
          "Paper simulation. No brokerage connection, no orders, no recommendations. Signals are unproven until backtested."}
      </span>
    </div>
  );
}
