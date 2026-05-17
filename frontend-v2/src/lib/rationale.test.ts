import { describe, expect, it } from 'vitest';
import { displayRationale } from './rationale';

describe('displayRationale', () => {
  it('keeps non-empty text', () => {
    expect(displayRationale('Tourism via 2 ELW; 3 landable')).toBe('Tourism via 2 ELW; 3 landable');
  });

  it('normalizes legacy refinery via-phrasing and removes ELW/WW', () => {
    const legacy = 'Strong Refinery; via 2 ELW, 2 WW, 4 ringed; 15 landable';

    const text = displayRationale(legacy);

    expect(text).not.toContain('ELW');
    expect(text).not.toContain('WW');
    expect(text).toContain('rebuild');
    expect(text).toContain('Strong Refinery');
  });

  it('preserves current rationale text without false legacy rewrite', () => {
    const current = 'Primary score: Strong Refinery (86); Factors: 4 rocky, 3 HMC';

    const text = displayRationale(current);

    expect(text).toBe(current);
  });
});
