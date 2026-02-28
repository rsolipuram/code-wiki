'use client';

/**
 * Backward-compat redirect: /[owner]/[name]/modules/[slug] → /[owner]/[name]/[slug]
 * Module content now lives in the unified wiki reader.
 */

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';

export default function ModuleRedirect() {
  const params = useParams();
  const router = useRouter();

  useEffect(() => {
    router.replace(`/${params.owner}/${params.name}/${params.slug}`);
  }, [params.owner, params.name, params.slug, router]);

  return null;
}
