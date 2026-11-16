"use client";

import { useCallback, useEffect, useState } from "react";
import { AreaMark } from "./area-mark";
import { areaById, type AreaId } from "@/lib/areas";

const CREDITS_EVENT = "wingman:credits";
const SHOW_MS = 5000;
const ACCENT = "#5b78b8";

const CONSOLE_SIGNATURE = [
  "\n%c  /\\  /\\  \n /  \\/  \\ \n/ Wingman \\\n",
  `color:${ACCENT};font-family:monospace;font-size:13px;font-weight:bold;`,
  `%cWingman Platform — Internal Developer Platform\nBuilt by ${areaById("wingman").credits.map((c) => c.name).join(" & ")}\n`,
  "font-family:monospace;font-size:11px;color:#888;",
];

/** The area's name as its brand writes it: Wingman's two-tone word and "Platform", any other area its name. */
function CardTitle({ area }: { area: AreaId }) {
  const grotesk = { fontFamily: "var(--font-grotesk)", letterSpacing: "-0.03em" };
  if (area !== "wingman") {
    return <div className="text-sm font-medium text-white" style={grotesk}>{areaById(area).brand.name}</div>;
  }
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

/** Who built the area, for five seconds or until clicked. */
function SignatureCard({ area, onClose }: { area: AreaId; onClose: () => void }) {
  const { brand, credits } = areaById(area);

  useEffect(() => {
    const t = setTimeout(onClose, SHOW_MS);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div
      data-testid="credits"
      data-area={area}
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
          <AreaMark mark={brand.mark} />
          <CardTitle area={area} />
        </div>

        <div className="h-px mb-3" style={{ background: "rgba(255,255,255,0.08)" }} />

        <div className="text-[10px] uppercase tracking-widest mb-0.5" style={{ color: "rgba(255,255,255,0.35)" }}>
          Built by
        </div>
        <div className="space-y-1.5">
          {credits.map(({ name, years }, i) => (
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
  const [area, setArea] = useState<AreaId | null>(null);
  const close = useCallback(() => setArea(null), []);

  useEffect(() => {
    if (!consolePrinted) {
      consolePrinted = true;
      console.log(...CONSOLE_SIGNATURE);
    }
  }, []);

  useEffect(() => {
    const handler = (e: Event) => setArea((e as CustomEvent<AreaId>).detail);
    window.addEventListener(CREDITS_EVENT, handler);
    return () => window.removeEventListener(CREDITS_EVENT, handler);
  }, []);

  if (!area) return null;
  return <SignatureCard key={area} area={area} onClose={close} />;
}

/** Show who built `area` (the brand's five quick clicks). */
export function triggerEasterEgg(area: AreaId) {
  window.dispatchEvent(new CustomEvent<AreaId>(CREDITS_EVENT, { detail: area }));
}
