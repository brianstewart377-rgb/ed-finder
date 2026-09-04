import { describe, expect, it } from 'vitest';
import { match } from './journey';

describe('journey route matcher', () => {
  it.each(['explore', 'inspect', 'plan', 'review'])(
    'accepts the %s journey',
    (journey) => {
      expect(match(journey)).toBe(true);
    },
  );

  it.each(['explroe', 'admin', '', 'Explore', 'review/export'])(
    'rejects the unknown %s journey',
    (journey) => {
      expect(match(journey)).toBe(false);
    },
  );
});
