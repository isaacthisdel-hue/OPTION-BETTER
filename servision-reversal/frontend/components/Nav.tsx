"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  ["01", "Scanner", "/"],
  ["02", "Candidates", "/candidates"],
  ["03", "Trades", "/paper-trades"],
  ["04", "Backtest", "/backtest"],
  ["05", "Statistics", "/stats"],
  ["06", "Settings", "/settings"],
  ["07", "Saved", "/saved"],
  ["08", "Replay", "/replay"],
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="nav">
      {ITEMS.map(([idx, label, href]) => (
        <Link key={href} href={href} className={path === href ? "active" : ""}>
          <span className="idx">{idx}</span>
          {label}
        </Link>
      ))}
    </nav>
  );
}
