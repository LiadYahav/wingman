"use client";

import { useCallback, useEffect, useState } from "react";
import { WINGMAN } from "@/lib/platforms";

const CREDITS_EVENT = "wingman:credits";
const SHOW_MS = 5000;
const ACCENT = "#5b78b8";

const CONSOLE_SIGNATURE = [
  "\n%c  /\\  /\\  \n /  \\/  \\ \n/ Wingman \\\n",
  `color:${ACCENT};font-family:monospace;font-size:13px;font-weight:bold;`,
  `%cWingman Platform — Internal Developer Platform\nBuilt by ${WINGMAN.credits.map((c) => c.name).join(" & ")}\n`,
  "font-family:monospace;font-size:11px;color:#888;",
];

/** Wingman's name as its brand writes it: the two-tone word and "Platform". */
function CardTitle() {
  const grotesk = { fontFamily: "var(--font-grotesk)", letterSpacing: "-0.03em" };
  return (
    <div>
      <div className="text-sm font-medium text-white" style={grotesk}>
        Wing<span style={{ color: ACCENT }}>man</span>
      </div>
      <div className="text-[10px] tracking-widest uppercase" style={{ color: ACCENT }}>
        Platform
      </div>
    </div>
  );
}

/** Who built Wingman, for five seconds or until clicked. */
function SignatureCard({ onClose }: { onClose: () => void }) {

  useEffect(() => {
    const t = setTimeout(onClose, SHOW_MS);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div
      data-testid="credits"
      role="status"
      className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-bottom-4 fade-in duration-300 motion-reduce:animate-none"
      onClick={onClose}
      style={{ cursor: "pointer" }}
    >
      <div
        className="rounded-2xl p-5 shadow-2xl w-60"
        style={{ background: "#0b1733", boxShadow: "0 20px 60px rgba(0,0,0,0.6)" }}
      >
        <div className="flex items-center gap-3 mb-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/wingman-logo.svg" alt="" width={32} height={32} className="h-8 w-8 shrink-0 rounded-lg" />
          <CardTitle />
        </div>

        <div className="h-px mb-3" style={{ background: "rgba(255,255,255,0.08)" }} />

        <div className="text-[10px] uppercase tracking-widest mb-0.5" style={{ color: "rgba(255,255,255,0.35)" }}>
          Built by
        </div>
        <div className="space-y-1.5">
          {WINGMAN.credits.map(({ name, years }, i) => (
            <div key={name} data-testid="credit">
              <div
                className="text-xl leading-snug text-white"
                style={{ fontFamily: "var(--font-grotesk)", fontWeight: 500, letterSpacing: "-0.03em" }}
              >
                {i > 0 && <span style={{ color: ACCENT }}>&amp; </span>}
                {name}
              </div>
              <div className="text-[10px]" style={{ color: "rgba(255,255,255,0.3)" }}>
                {years}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

let consolePrinted = false;

export function EasterEgg() {
  const [shown, setShown] = useState(false);
  const close = useCallback(() => setShown(false), []);

  useEffect(() => {
    if (!consolePrinted) {
      consolePrinted = true;
      console.log(...CONSOLE_SIGNATURE);
    }
  }, []);

  useEffect(() => {
    const handler = () => setShown(true);
    window.addEventListener(CREDITS_EVENT, handler);
    return () => window.removeEventListener(CREDITS_EVENT, handler);
  }, []);

  if (!shown) return null;
  return <SignatureCard onClose={close} />;
}

/** Show who built Wingman (the brand's five quick clicks). */
export function triggerEasterEgg() {
  window.dispatchEvent(new Event(CREDITS_EVENT));
}
