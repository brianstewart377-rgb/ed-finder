import { useMemo } from 'react';
import type { SystemBody } from '../../../types/api';
import { bodyThumbnailParams } from './bodyThumbnailParams';
import { renderBodyThumbnail, seedFromBody } from './renderBodyThumbnail';

const SIZE = 36;

// A small procedural planet/star preview for a body. Renders the WebGL thumbnail
// (cached, deterministic per body) when available, otherwise a typed CSS disc so
// no-WebGL environments and tests still show a recognisable, deterministic dot.
export function BodyThumbnail({ body }: { body: SystemBody }) {
  const params = useMemo(() => bodyThumbnailParams(body), [body]);
  const seed = useMemo(() => seedFromBody(body.id ?? body.name), [body.id, body.name]);
  // Render at 2x for crispness on HiDPI, display at SIZE.
  const url = useMemo(
    () => (params.kind === 'none' ? '' : renderBodyThumbnail(params, seed, SIZE * 2)),
    [params, seed],
  );

  if (params.kind === 'none') {
    return <span data-body-thumb="none" aria-hidden style={{ display: 'inline-block', width: SIZE, height: SIZE }} />;
  }

  const title = params.kind === 'star' ? 'Star' : undefined;

  if (url) {
    return (
      <img
        data-body-thumb="img"
        src={url}
        width={SIZE}
        height={SIZE}
        alt=""
        aria-hidden
        title={title}
        style={{ borderRadius: '50%', display: 'block' }}
      />
    );
  }

  // No-WebGL fallback: a deterministic CSS disc in the body's own colors.
  return (
    <span
      data-body-thumb="css"
      aria-hidden
      title={title}
      style={{
        display: 'inline-block',
        width: SIZE,
        height: SIZE,
        borderRadius: '50%',
        background: `radial-gradient(circle at 34% 30%, ${params.accent}, ${params.base} 68%)`,
        boxShadow: params.kind === 'star' ? `0 0 6px ${params.base}` : 'none',
      }}
    />
  );
}
