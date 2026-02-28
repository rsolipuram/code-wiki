'use client';

/**
 * TableOfContents — scroll-spy TOC matching mock .toc-item styles.
 *
 * Mock reference: specs/001-code-wiki/ux/docs-glassmorphism/module.html
 * Active item: color = primary-light, gradient left border (height 100%).
 */

import { useEffect, useState } from 'react';
import styles from './TableOfContents.module.css';

export interface TocEntry {
  id: string;
  label: string;
  level?: number;
}

interface TableOfContentsProps {
  entries?: TocEntry[];
  items?: TocEntry[];
}

export function TableOfContents({ entries, items }: TableOfContentsProps) {
  const resolvedEntries = entries ?? items ?? [];
  const [activeId, setActiveId] = useState<string>('');

  useEffect(() => {
    const observer = new IntersectionObserver(
      (obs) => {
        // Find topmost visible heading
        const visible = obs.filter((e) => e.isIntersecting);
        if (visible.length > 0) {
          setActiveId(visible[0].target.id);
        }
      },
      { rootMargin: '-10% 0px -80% 0px', threshold: 0 }
    );

    resolvedEntries.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });

    return () => observer.disconnect();
  }, [resolvedEntries]);

  if (resolvedEntries.length === 0) return null;

  return (
    <nav className={styles.tocNav}>
      <h4 className={styles.tocTitle}>On This Page</h4>
      <div className={styles.tocList}>
        {resolvedEntries.map(({ id, label, level = 2 }) => (
          <a
            key={id}
            href={`#${id}`}
            className={`${styles.tocItem} ${level === 3 ? styles.level3 : ''} ${
              activeId === id ? styles.active : ''
            }`}
          >
            {label}
          </a>
        ))}
      </div>
    </nav>
  );
}
