'use client';

/**
 * Function / Entity detail page — signature, params, call graph, source.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/function.html
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { GradientBackground } from '@/components/ui/GradientBackground';
import { Logo } from '@/components/ui/Logo';
import { Breadcrumbs } from '@/components/ui/Breadcrumbs';
import { CodeBlock } from '@/components/ui/CodeBlock';
import { TypeBadge } from '@/components/ui/TypeBadge';
import { TableOfContents } from '@/components/layout/TableOfContents';
import { WikiSidebar } from '@/components/layout/WikiSidebar';
import { api } from '@/services/api';
import type { CodeEntity, Repository } from '@/services/api';

const TOC_ITEMS = [
  { id: 'signature', label: 'Signature', level: 2 },
  { id: 'parameters', label: 'Parameters', level: 2 },
  { id: 'return-value', label: 'Return Value', level: 2 },
  { id: 'examples', label: 'Usage Examples', level: 2 },
  { id: 'called-by', label: 'Called By', level: 2 },
  { id: 'calls', label: 'Calls', level: 2 },
  { id: 'source', label: 'Source Code', level: 2 },
];

const SIDEBAR_SECTIONS = [
  {
    label: 'Getting Started',
    items: [
      { label: 'Overview', href: 'getting-started' },
      { label: 'Quick Start', href: 'getting-started' },
    ],
  },
  {
    label: 'Core Concepts',
    items: [
      { label: 'Repository Analysis', href: 'modules/analysis' },
      { label: 'Module Detection', href: 'modules/detection' },
    ],
  },
  {
    label: 'API Reference',
    items: [
      { label: 'Function Index', href: 'api' },
      { label: 'Glossary', href: 'glossary' },
    ],
  },
];


export default function EntityPage() {
  const params = useParams();
  const owner = params.owner as string;
  const name = params.name as string;
  const entityName = params.entityName as string;

  const [repo, setRepo] = useState<Repository | null>(null);
  const [entity, setEntity] = useState<CodeEntity | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const { repositories } = await api.repositories.list();
        const found = repositories.find(
          (r) => r.owner?.toLowerCase() === owner.toLowerCase() && r.name.toLowerCase() === name.toLowerCase()
        );
        if (!found) { setLoading(false); return; }
        setRepo(found);
        const ent = await api.wikis.getEntity(found.id, entityName).catch(() => null);
        setEntity(ent);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [owner, name, entityName]);

  const displayName = entity?.name ?? entityName;
  const displayType = entity?.entity_type ?? 'function';
  const base = `/${owner}/${name}`;

  const signature = entity?.signature ??
    `async function ${displayName}(\n  username: string,\n  password: string,\n  options?: AuthOptions\n): Promise<AuthResult>`;

  const filePath = entity?.file_path ?? `src/auth/${entityName}.ts`;
  const lineNumber = entity?.line_number ?? 42;

  // relationships.calls = what this entity calls (outgoing edges in CALLS graph)
  // relationships.imports = modules/files this entity imports
  const callees: string[] = entity?.relationships?.calls ?? [];
  const imports: string[] = entity?.relationships?.imports ?? [];

  const tableStyle: React.CSSProperties = {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: 14,
    marginBottom: 8,
  };

  const thStyle: React.CSSProperties = {
    textAlign: 'left',
    padding: '10px 14px',
    fontSize: 12,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: 'var(--text-tertiary)',
    borderBottom: '1px solid var(--glass-border)',
    background: 'rgba(255,255,255,0.03)',
  };

  const tdStyle: React.CSSProperties = {
    padding: '12px 14px',
    borderBottom: '1px solid var(--glass-border)',
    color: 'var(--text-secondary)',
    verticalAlign: 'top',
  };

  return (
    <>
      <GradientBackground />

      <div
        className="wiki-layout"
        style={{
          display: 'grid',
          gridTemplateColumns: '280px 1fr 260px',
          minHeight: '100vh',
        }}
      >
        {/* ── Left sidebar ── */}
        <WikiSidebar pageTitle={`${name} — ${displayName}`}>
          <div style={{ padding: '0 20px 20px' }}>
            <Logo href={base} />
          </div>

          {/* Back to module */}
          <div style={{ padding: '0 20px 16px' }}>
            <Link
              href={`${base}/modules/auth`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 13,
                color: 'var(--text-tertiary)',
                textDecoration: 'none',
                transition: 'color 0.2s',
              }}
            >
              ← Authentication Module
            </Link>
          </div>

          {SIDEBAR_SECTIONS.map((section) => (
            <div key={section.label} style={{ marginBottom: 8 }}>
              <div
                style={{
                  padding: '6px 20px',
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.8px',
                  color: 'var(--text-tertiary)',
                }}
              >
                {section.label}
              </div>
              {section.items.map((item) => (
                <Link
                  key={item.label}
                  href={`${base}/${item.href}`}
                  style={{
                    display: 'block',
                    padding: '8px 20px',
                    fontSize: 14,
                    fontWeight: 500,
                    color: 'var(--text-secondary)',
                    textDecoration: 'none',
                    transition: 'color 0.2s',
                  }}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          ))}
        </WikiSidebar>

        {/* ── Main content ── */}
        <main
          className="wiki-main"
          style={{
            padding: '32px 44px',
            minWidth: 0,
            background: 'var(--glass-bg)',
            backdropFilter: 'blur(20px)',
            borderRight: '1px solid var(--glass-border)',
          }}
        >
          <Breadcrumbs
            crumbs={[
              { label: `${name} wiki`, href: base },
              { label: 'Modules', href: `${base}/modules` },
              { label: 'Authentication', href: `${base}/modules/auth` },
              { label: displayName },
            ]}
          />

          {/* Function header */}
          <div style={{ marginTop: 28, marginBottom: 32 }}>
            <TypeBadge type={displayType as 'function' | 'class' | 'method' | 'module'} style={{ marginBottom: 12 }} />
            <h1
              style={{
                fontFamily: "'Fira Code', monospace",
                fontSize: 30,
                fontWeight: 700,
                letterSpacing: '-0.02em',
                marginBottom: 12,
              }}
            >
              {displayName}
            </h1>
            <p style={{ color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 16, maxWidth: 700 }}>
              {entity?.docstring ??
                'Authenticates a user with their credentials, validates against the database, and generates a JWT token for session management. Supports both traditional username/password authentication and OAuth providers.'}
            </p>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 13, color: 'var(--text-tertiary)' }}>
              <span>📁 {filePath}</span>
              <span>📏 Lines {lineNumber}–{lineNumber + 45}</span>
              <span>👤 {entity?.visibility ?? 'Public'} API</span>
            </div>
          </div>

          {/* Signature */}
          <h2 id="signature" style={{ fontSize: 20, fontWeight: 700, marginBottom: 14 }}>
            Signature
          </h2>
          <div
            style={{
              background: 'rgba(0,0,0,0.4)',
              border: '1px solid var(--glass-border)',
              borderRadius: 12,
              padding: '20px 24px',
              fontFamily: "'Fira Code', monospace",
              fontSize: 14,
              lineHeight: 1.8,
              marginBottom: 32,
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
            }}
          >
            <span style={{ color: '#A78BFA' }}>async </span>
            <span style={{ color: '#A78BFA' }}>function </span>
            <span style={{ color: '#06B6D4' }}>{displayName}</span>
            {'(\n  '}
            <span style={{ color: '#F9FAFB' }}>username</span>
            <span style={{ color: '#9CA3AF' }}>: </span>
            <span style={{ color: '#10B981' }}>string</span>
            {',\n  '}
            <span style={{ color: '#F9FAFB' }}>password</span>
            <span style={{ color: '#9CA3AF' }}>: </span>
            <span style={{ color: '#10B981' }}>string</span>
            {',\n  '}
            <span style={{ color: '#F9FAFB' }}>options</span>
            <span style={{ color: '#9CA3AF' }}>?: </span>
            <span style={{ color: '#10B981' }}>AuthOptions</span>
            {'\n)'}
            <span style={{ color: '#9CA3AF' }}>: </span>
            <span style={{ color: '#10B981' }}>Promise</span>
            <span style={{ color: '#9CA3AF' }}>&lt;</span>
            <span style={{ color: '#10B981' }}>AuthResult</span>
            <span style={{ color: '#9CA3AF' }}>&gt;</span>
          </div>

          {/* Parameters */}
          {entity?.docstring && (
            <>
              <h2 id="description" style={{ fontSize: 20, fontWeight: 700, marginBottom: 14 }}>
                Description
              </h2>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 32, fontFamily: "'Crimson Pro', Georgia, serif", fontSize: 16 }}>
                {entity.docstring}
              </p>
            </>
          )}

          {/* Relationships — only shown when real data exists */}
          {[
            { id: 'calls', title: 'Calls', items: callees.map((n) => ({ name: n, location: '' })) },
            { id: 'imports', title: 'Imports', items: imports.map((n) => ({ name: n, location: '' })) },
          ].filter((g) => g.items.length > 0).map((group) => (
            <div key={group.id}>
              <h2 id={group.id} style={{ fontSize: 20, fontWeight: 700, marginBottom: 14 }}>
                {group.title}
              </h2>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                  gap: 12,
                  marginBottom: 32,
                }}
              >
                {group.items.map((item) => (
                  <Link
                    key={item.name}
                    href={`${base}/entities/${item.name.replace('()', '')}`}
                    style={{
                      padding: '16px',
                      background: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--glass-border)',
                      borderRadius: 12,
                      textDecoration: 'none',
                      transition: 'all 0.2s',
                    }}
                    onMouseOver={(e) => {
                      e.currentTarget.style.borderColor = 'rgba(6,182,212,0.4)';
                      e.currentTarget.style.background = 'rgba(6,182,212,0.05)';
                    }}
                    onMouseOut={(e) => {
                      e.currentTarget.style.borderColor = 'var(--glass-border)';
                      e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
                    }}
                  >
                    <div
                      style={{
                        fontFamily: "'Fira Code', monospace",
                        fontSize: 13,
                        color: 'var(--secondary)',
                        fontWeight: 600,
                        marginBottom: 6,
                      }}
                    >
                      {item.name}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                      {item.location}
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          ))}

          {/* Source Code */}
          <h2 id="source" style={{ fontSize: 20, fontWeight: 700, marginBottom: 14 }}>
            Source Code
          </h2>
          <CodeBlock language="typescript">
            {`async function ${displayName}(\n  username: string,\n  password: string,\n  options?: AuthOptions\n): Promise<AuthResult> {\n  const user = await findUserByCredentials(username);\n  if (!user) return { success: false, error: 'INVALID_CREDENTIALS' };\n\n  const valid = await hashPassword.verify(password, user.passwordHash);\n  if (!valid) return { success: false, error: 'INVALID_CREDENTIALS' };\n\n  const token = await generateJWT({ userId: user.id }, options);\n  return { success: true, token, user };\n}`}
          </CodeBlock>
        </main>

        {/* ── Right TOC ── */}
        <aside
          style={{
            position: 'sticky',
            top: 0,
            height: '100vh',
            overflowY: 'auto',
            padding: '32px 20px',
          }}
        >
          <TableOfContents entries={TOC_ITEMS} />
        </aside>
      </div>
    </>
  );
}
