'use client';

/**
 * Sidebar — navigation component matching mock .sidebar-left content.
 *
 * Mock reference: specs/001-code-wiki/ux/docs-glassmorphism/module.html
 * Nav item: translateX(4px) on hover, gradient background on active,
 * box-shadow: 0 0 20px rgba(139,92,246,0.3) on active.
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import styles from './Sidebar.module.css';
import { Logo } from '../ui/Logo';

export interface NavItem {
  label: string;
  href: string;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

interface SidebarProps {
  sections: NavSection[];
  repoName?: string;
  repoOwner?: string;
  repoHref?: string;
}

export function Sidebar({ sections, repoName, repoOwner, repoHref = '/' }: SidebarProps) {
  const pathname = usePathname();

  return (
    <nav className={styles.sidebarNav}>
      {/* Logo + repo name */}
      <div className={styles.sidebarHeader}>
        <Logo href="/" size="sm" />
      </div>

      {repoName && (
        <div className={styles.repoInfo}>
          <span className={styles.repoOwner}>{repoOwner}</span>
          <Link href={repoHref} className={styles.repoName}>
            {repoName}
          </Link>
        </div>
      )}

      {/* Nav sections */}
      {sections.map((section, i) => (
        <div
          key={section.title}
          className={`${styles.navSection} animate-fade-in-up`}
          style={{ animationDelay: `${i * 0.1}s` }}
        >
          <h3 className={styles.navSectionTitle}>{section.title}</h3>
          <div className={styles.navItems}>
            {section.items.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
                >
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
