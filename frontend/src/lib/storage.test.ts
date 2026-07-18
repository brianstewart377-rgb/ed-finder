import { afterEach, describe, expect, it, vi } from 'vitest';
import { readLocalStorage, removeLocalStorage, writeLocalStorage } from './storage';

describe('safe local storage helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('reads, writes, and removes values', () => {
    expect(writeLocalStorage('test-key', '42')).toBe(true);
    expect(readLocalStorage('test-key')).toBe('42');
    expect(removeLocalStorage('test-key')).toBe(true);
    expect(readLocalStorage('test-key')).toBeNull();
  });

  it('fails closed when browser storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });

    expect(readLocalStorage('test-key')).toBeNull();
    expect(writeLocalStorage('test-key', '42')).toBe(false);
    expect(removeLocalStorage('test-key')).toBe(false);
  });
});
