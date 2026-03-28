"use client";

import Link from "next/link";
import React from "react";

interface CrossRefLinkProps {
  /** Display text from <cross-ref> tag content */
  text: string;
  /** Section title used for aria-label */
  sectionTitle: string;
  /** Section slug — used to build the href if owner/name are available */
  sectionSlug: string;
  /** Repository owner (from URL params) */
  owner?: string;
  /** Repository name (from URL params) */
  repoName?: string;
  /** Fallback: if slug resolution failed, render as plain span */
  unresolved?: boolean;
}

export function CrossRefLink({
  text,
  sectionTitle,
  sectionSlug,
  owner,
  repoName,
  unresolved = false,
}: CrossRefLinkProps) {
  if (unresolved || !sectionSlug || !owner || !repoName) {
    return (
      <span
        className="text-white/50 italic"
        title={`Unresolved cross-reference: ${sectionTitle}`}
      >
        {text || sectionTitle}
      </span>
    );
  }

  const href = `/${owner}/${repoName}/wiki/${sectionSlug}`;

  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1 rounded bg-white/10 px-1.5 py-0.5 text-blue-300 hover:bg-white/20 hover:text-blue-200 transition-colors no-underline"
      aria-label={`Go to section: ${sectionTitle}`}
    >
      <span className="text-xs text-white/40" aria-hidden="true">→</span>
      {text || sectionTitle}
    </Link>
  );
}
