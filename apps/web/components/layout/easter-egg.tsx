"use client";

import { useEffect, useState } from "react";

const CONSOLE_SIGNATURE = [
  "\n%c  /\\  /\\  \n /  \\/  \\ \n/ Wingman \\\n",
  "color:#5b78b8;font-family:monospace;font-size:13px;font-weight:bold;",
  "%cWingman Platform — Internal Developer Platform\nBuilt by Liad Yahav\n",
  "font-family:monospace;font-size:11px;color:#888;",
];

function SignatureCard({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 5000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div
      className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-bottom-4 fade-in duration-300"
      onClick={onClose}
      style={{ cursor: "pointer" }}
    >
      <div
        className="rounded-2xl p-5 shadow-2xl w-60"
        style={{ background: "#0b1733", boxShadow: "0 20px 60px rgba(0,0,0,0.6)" }}
      >
        <div className="flex items-center gap-3 mb-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/wingman-logo.svg" width={36} height={36} alt="" className="rounded-lg" />
          <div>
            <div
              className="text-sm font-medium text-white"
              style={{ fontFamily: "var(--font-grotesk)", letterSpacing: "-0.03em" }}
            >
              Wing<span style={{ color: "#5b78b8" }}>man</span>
            </div>
            <div className="text-[10px] tracking-widest uppercase" style={{ color: "#5b78b8" }}>
              Platform
            </div>
          </div>
        </div>

        <div className="h-px mb-3" style={{ background: "rgba(255,255,255,0.08)" }} />

        <div className="text-[10px] uppercase tracking-widest mb-0.5" style={{ color: "rgba(255,255,255,0.35)" }}>
          Built by
        </div>
        <div
          className="text-xl text-white"
          style={{ fontFamily: "var(--font-grotesk)", fontWeight: 500, letterSpacing: "-0.03em" }}
        >
          Liad Yahav
        </div>
        <div className="text-[10px] mt-1" style={{ color: "rgba(255,255,255,0.3)" }}>
          2024 – 2026
        </div>
      </div>
    </div>
  );
}

let consolePrinted = false;

export function EasterEgg() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!consolePrinted) {
      consolePrinted = true;
      console.log(...CONSOLE_SIGNATURE);
    }
  }, []);

  useEffect(() => {
    const handler = () => setVisible(true);
    window.addEventListener("wingman:credits", handler);
    return () => window.removeEventListener("wingman:credits", handler);
  }, []);

  if (!visible) return null;
  return <SignatureCard onClose={() => setVisible(false)} />;
}

export function triggerEasterEgg() {
  window.dispatchEvent(new Event("wingman:credits"));
}
