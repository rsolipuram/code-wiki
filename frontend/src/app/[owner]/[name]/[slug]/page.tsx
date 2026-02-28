'use client';

/**
 * Wiki section page — renders the unified wiki reader for the given slug.
 * Handles modules, getting-started, glossary, api-reference, etc.
 *
 * Static routes (chat, search, progress, entities) take precedence
 * in Next.js App Router, so this only matches wiki content slugs.
 */

import { useParams } from 'next/navigation';
import WikiReader from '../WikiReader';

export default function WikiSectionPage() {
  const params = useParams();
  return (
    <WikiReader
      owner={params.owner as string}
      name={params.name as string}
      slug={params.slug as string}
    />
  );
}
