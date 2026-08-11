import { describe, it, expect } from 'vitest';
import type { SystemBody } from '../../../types/api';
import { bodyThumbnailParams, spectralStarColor } from './bodyThumbnailParams';

const body = (overrides: Partial<SystemBody>): SystemBody => overrides as SystemBody;

describe('bodyThumbnailParams', () => {
  it('skips barycentres', () => {
    expect(bodyThumbnailParams(body({ body_type: 'Barycentre' })).kind).toBe('none');
  });

  it('renders stars as glowing, colored by spectral class', () => {
    const m = bodyThumbnailParams(body({ body_type: 'Star', spectral_class: 'M5 V' }));
    expect(m.kind).toBe('star');
    expect(m.base).toBe(spectralStarColor('M'));
    const g = bodyThumbnailParams(body({ body_type: 'Star', spectral_class: 'G2 V' }));
    expect(g.base).toBe(spectralStarColor('G'));
    expect(g.base).not.toBe(m.base);
  });

  it('classes earth-like and water worlds with an atmosphere', () => {
    expect(bodyThumbnailParams(body({ body_type: 'Planet', is_earth_like: true })).atmosphere).toBe(true);
    const w = bodyThumbnailParams(body({ body_type: 'Planet', is_water_world: true }));
    expect(w.kind).toBe('planet');
    expect(w.atmosphere).toBe(true);
    expect(w.gasGiant).toBe(false);
  });

  it('detects gas giants from subtype and gives class I/II rings', () => {
    const g = bodyThumbnailParams(body({ body_type: 'Planet', subtype: 'Sudarsky class II gas giant' }));
    expect(g.gasGiant).toBe(true);
    expect(g.rings).toBe(true);
    const g3 = bodyThumbnailParams(body({ body_type: 'Planet', subtype: 'Sudarsky class III gas giant' }));
    expect(g3.gasGiant).toBe(true);
    expect(g3.rings).toBe(false);
  });

  it('classes rocky / metal / icy planets without gas or (usually) atmosphere', () => {
    expect(bodyThumbnailParams(body({ body_type: 'Planet', subtype: 'High metal content world' })).gasGiant).toBe(false);
    expect(bodyThumbnailParams(body({ body_type: 'Planet', subtype: 'Rocky body' })).kind).toBe('planet');
    expect(bodyThumbnailParams(body({ body_type: 'Planet', subtype: 'Icy body' })).atmosphere).toBe(true);
  });

  it('returns none for an unknown body with no subtype', () => {
    expect(bodyThumbnailParams(body({ body_type: 'Unknown', subtype: '' })).kind).toBe('none');
  });
});

describe('spectralStarColor', () => {
  it('maps the first spectral letter and defaults for unknown', () => {
    expect(spectralStarColor('O9 V')).toBe('#9bb0ff');
    expect(spectralStarColor('m')).toBe('#ffb37a');
    expect(spectralStarColor(null)).toBe('#ffe0b0');
    expect(spectralStarColor('???')).toBe('#ffe0b0');
  });
});
