'use client';

/**
 * ThreeColumnLayout — 300px | 1fr | 280px grid matching mock .docs-layout.
 *
 * Mock reference: specs/001-code-wiki/ux/docs-glassmorphism/module.html
 * Breakpoints: <1400px hides right TOC, <900px collapses to single column.
 */

import { type ReactNode } from 'react';
import styles from './ThreeColumnLayout.module.css';

interface ThreeColumnLayoutProps {
  sidebar: ReactNode;
  main: ReactNode;
  toc?: ReactNode;
}

export function ThreeColumnLayout({ sidebar, main, toc }: ThreeColumnLayoutProps) {
  return (
    <div className={styles.docsLayout}>
      <aside className={`${styles.sidebarLeft} glass-card`}>{sidebar}</aside>
      <main className={styles.mainContent}>{main}</main>
      {toc && (
        <aside className={`${styles.sidebarRight} glass-card`}>{toc}</aside>
      )}
    </div>
  );
}
