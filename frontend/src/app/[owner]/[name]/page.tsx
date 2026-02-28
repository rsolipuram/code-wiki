'use client';

/**
 * Wiki home — unified wiki reader showing the overview section.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/module.html
 */

import { useParams } from 'next/navigation';
import WikiReader from './WikiReader';

export default function WikiHomePage() {
  const params = useParams();
  return (
    <WikiReader
      owner={params.owner as string}
      name={params.name as string}
    />
  );
}
