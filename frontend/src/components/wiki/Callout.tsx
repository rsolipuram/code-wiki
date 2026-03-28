"use client";

import React from "react";

export type CalloutType = "warning" | "info" | "tip";

interface CalloutProps {
  type: CalloutType;
  children: React.ReactNode;
}

const VARIANTS: Record<
  CalloutType,
  { border: string; bg: string; icon: string; label: string; text: string }
> = {
  warning: {
    border: "border-amber-500/60",
    bg: "bg-amber-500/10",
    icon: "⚠️",
    label: "Warning",
    text: "text-amber-300",
  },
  info: {
    border: "border-blue-500/60",
    bg: "bg-blue-500/10",
    icon: "ℹ️",
    label: "Note",
    text: "text-blue-300",
  },
  tip: {
    border: "border-green-500/60",
    bg: "bg-green-500/10",
    icon: "💡",
    label: "Tip",
    text: "text-green-300",
  },
};

export function Callout({ type, children }: CalloutProps) {
  const v = VARIANTS[type] ?? VARIANTS.info;
  return (
    <div
      className={`my-4 rounded-lg border ${v.border} ${v.bg} px-4 py-3`}
      role="note"
      aria-label={v.label}
    >
      <div className={`mb-1 flex items-center gap-2 text-sm font-semibold ${v.text}`}>
        <span aria-hidden="true">{v.icon}</span>
        {v.label}
      </div>
      <div className="text-sm text-white/80">{children}</div>
    </div>
  );
}
