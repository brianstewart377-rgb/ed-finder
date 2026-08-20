import { describe, it, expect } from 'vitest';
import { spectralStarColor } from '../spectralStarColor';

describe('spectralStarColor', () => {
  it('maps each MK spectral letter to its documented RGB triple', () => {
    expect(spectralStarColor('O')).toEqual({ r: 0.6, g: 0.8, b: 1.0 });
    expect(spectralStarColor('B')).toEqual({ r: 0.7, g: 0.85, b: 1.0 });
    expect(spectralStarColor('A')).toEqual({ r: 0.85, g: 0.9, b: 1.0 });
    expect(spectralStarColor('F')).toEqual({ r: 0.95, g: 0.95, b: 1.0 });
    expect(spectralStarColor('G')).toEqual({ r: 1.0, g: 1.0, b: 0.9 });
    expect(spectralStarColor('K')).toEqual({ r: 1.0, g: 0.8, b: 0.6 });
    expect(spectralStarColor('M')).toEqual({ r: 1.0, g: 0.6, b: 0.4 });
  });

  it('reads only the first character, case-insensitively, of a full class string', () => {
    expect(spectralStarColor('M2 V')).toEqual(spectralStarColor('M'));
    expect(spectralStarColor('g')).toEqual(spectralStarColor('G'));
  });

  it('defaults to G for unknown, empty, or missing classes', () => {
    expect(spectralStarColor('???')).toEqual(spectralStarColor('G'));
    expect(spectralStarColor('')).toEqual(spectralStarColor('G'));
    expect(spectralStarColor(null)).toEqual(spectralStarColor('G'));
    expect(spectralStarColor(undefined)).toEqual(spectralStarColor('G'));
  });
});
