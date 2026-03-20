'use client';

/**
 * CodeBlock — Fira Code, dark bg, copy button matching mock pre/code styles.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/module.html
 */

import { useState, type ReactNode } from 'react';

interface CodeBlockProps {
  code?: string;
  children?: ReactNode;
  language?: string;
}

export function CodeBlock({ code, children, language }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const content = String(children ?? code ?? '');
  const lines = content.split('\n');
  const MAX_VISIBLE_LINES = 16;
  const isLong = lines.length > MAX_VISIBLE_LINES;
  const visibleContent = !isLong || expanded
    ? content
    : `${lines.slice(0, MAX_VISIBLE_LINES).join('\n')}\n…`;

  const copy = async () => {
    await navigator.clipboard.writeText(String(code ?? children ?? ''));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ position: 'relative', margin: '32px 0' }}>
      {/* Language label */}
      {language && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            left: 24,
            fontSize: 12,
            fontFamily: "'Fira Code', monospace",
            color: 'var(--text-tertiary)',
            letterSpacing: '0.05em',
            textTransform: 'lowercase',
          }}
        >
          {language}
        </div>
      )}

      {/* Copy button */}
      <button
        onClick={copy}
        style={{
          position: 'absolute',
          top: 12,
          right: 16,
          background: 'rgba(139,92,246,0.15)',
          border: '1px solid rgba(139,92,246,0.3)',
          borderRadius: 8,
          color: copied ? 'var(--success)' : 'var(--primary-light)',
          fontFamily: "'Outfit', sans-serif",
          fontSize: 12,
          fontWeight: 600,
          padding: '4px 12px',
          cursor: 'pointer',
          transition: 'all 0.2s',
        }}
      >
        {copied ? '✓ Copied' : 'Copy'}
      </button>
      {isLong && (
        <button
          onClick={() => setExpanded((prev) => !prev)}
          style={{
            position: 'absolute',
            top: 12,
            right: 84,
            background: 'rgba(255,255,255,0.08)',
            border: '1px solid var(--glass-border)',
            borderRadius: 8,
            color: 'var(--text-secondary)',
            fontFamily: "'Outfit', sans-serif",
            fontSize: 12,
            fontWeight: 600,
            padding: '4px 12px',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
        >
          {expanded ? 'Collapse' : `Expand (${lines.length} lines)`}
        </button>
      )}

      <pre
        style={{
          background: 'rgba(5,5,8,0.8)',
          padding: '28px',
          paddingTop: language ? '48px' : '28px',
          borderRadius: 16,
          overflowX: 'auto',
          fontFamily: "'Fira Code', monospace",
          fontSize: 14,
          lineHeight: 1.8,
          border: '1px solid var(--glass-border)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        }}
      >
        <code style={{ color: '#E5E7EB', background: 'none', border: 'none', padding: 0 }}>
          {visibleContent}
        </code>
      </pre>
    </div>
  );
}
