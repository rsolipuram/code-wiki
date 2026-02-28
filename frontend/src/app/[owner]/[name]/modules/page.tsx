'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';

/**
 * /[owner]/[name]/modules — redirect to wiki home which lists all modules.
 */
export default function ModulesIndexPage() {
  const params = useParams();
  const router = useRouter();

  useEffect(() => {
    router.replace(`/${params.owner}/${params.name}`);
  }, [params.owner, params.name, router]);

  return null;
}
