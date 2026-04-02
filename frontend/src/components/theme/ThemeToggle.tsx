"use client";

import { useTheme } from "@/components/theme/ThemeProvider";
import type { CSSProperties } from "react";

type ThemeToggleProps = {
  className?: string;
  style?: CSSProperties;
};

export function ThemeToggle({ className, style }: ThemeToggleProps) {
  const { toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "10px 16px",
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        borderRadius: 12,
        cursor: "pointer",
        fontSize: 14,
        fontWeight: 600,
        color: "var(--text-secondary)",
        fontFamily: "'Outfit', sans-serif",
        ...style,
      }}
      aria-label="Toggle theme"
      title="Toggle theme"
    >
      Theme
    </button>
  );
}
