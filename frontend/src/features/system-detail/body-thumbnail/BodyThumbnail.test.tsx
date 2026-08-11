import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import type { SystemBody } from '../../../types/api';
import { BodyThumbnail } from './BodyThumbnail';

const body = (overrides: Partial<SystemBody>): SystemBody => overrides as SystemBody;

// jsdom has no WebGL, so renderBodyThumbnail returns '' and the component falls
// back to the deterministic CSS disc — which is what we assert here.
describe('BodyThumbnail', () => {
  it('renders a typed CSS disc fallback when WebGL is unavailable', () => {
    const { container } = render(<BodyThumbnail body={body({ body_type: 'Planet', subtype: 'Rocky body', id: 1 })} />);
    const el = container.querySelector('[data-body-thumb]');
    expect(el).not.toBeNull();
    expect(el?.getAttribute('data-body-thumb')).toBe('css');
    expect((el as HTMLElement).style.borderRadius).toBe('50%');
  });

  it('renders an empty placeholder (not a disc) for a barycentre', () => {
    const { container } = render(<BodyThumbnail body={body({ body_type: 'Barycentre', id: 2 })} />);
    expect(container.querySelector('[data-body-thumb="none"]')).not.toBeNull();
    expect(container.querySelector('[data-body-thumb="css"]')).toBeNull();
  });

  it('does not throw and renders a thumbnail element for a star', () => {
    const { container } = render(<BodyThumbnail body={body({ body_type: 'Star', spectral_class: 'G2 V', id: 3 })} />);
    const el = container.querySelector('[data-body-thumb]');
    expect(el).not.toBeNull();
    expect(el?.getAttribute('title')).toBe('Star');
  });
});
