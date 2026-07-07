const COALSACK_BG_VERSION = 'v=2';
const COALSACK_BG_2560 = 'coalsack-2560.jpg';
const COALSACK_BG_1600 = 'coalsack-1600.jpg';

function isLocalDevHost(): boolean {
  return typeof window !== 'undefined'
    && ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
}

function coalsackBackgroundCandidates(fileName: string): string[] {
  const base = import.meta.env.BASE_URL || '/';
  const normalizedBase = base.endsWith('/') ? base : `${base}/`;

  const candidates = [
    `${normalizedBase}bg/${fileName}?${COALSACK_BG_VERSION}`,
    `/bg/${fileName}?${COALSACK_BG_VERSION}`,
  ];

  return Array.from(new Set(candidates));
}

async function resolveCoalsackBackgroundUrl(fileName: string): Promise<string> {
  const candidates = coalsackBackgroundCandidates(fileName);
  if (isLocalDevHost()) return candidates[0];
  if (typeof fetch !== 'function') return candidates[0];

  for (const candidate of candidates) {
    try {
      const response = await fetch(candidate, { method: 'HEAD', cache: 'no-cache' });
      const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
      if (response.ok && contentType.startsWith('image/')) {
        return candidate;
      }
    } catch {
      continue;
    }
  }

  return candidates[0];
}

export function setCoalsackBackgroundVariables(): () => void {
  let cancelled = false;
  const root = document.documentElement;

  void resolveCoalsackBackgroundUrl(COALSACK_BG_2560).then((url) => {
    if (!cancelled) root.style.setProperty('--coalsack-bg-2560', `url("${url}")`);
  });

  void resolveCoalsackBackgroundUrl(COALSACK_BG_1600).then((url) => {
    if (!cancelled) root.style.setProperty('--coalsack-bg-1600', `url("${url}")`);
  });

  return () => {
    cancelled = true;
  };
}
