import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GalaxyStarRequests } from './galaxy-star-requests';

function deferred() {
  let resolve!: (value: string) => void;
  const promise = new Promise<string>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('bounded catalogue cell requests', () => {
  let requests: GalaxyStarRequests;
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    requests = new GalaxyStarRequests();
  });
  afterEach(() => {
    requests.dispose();
    expect(vi.getTimerCount()).toBe(0);
    vi.useRealTimers();
  });

  it('runs at most four downloads concurrently and fills released slots in queue order', async () => {
    const downloads = Array.from({ length: 6 }, () => deferred());
    const order: number[] = [];
    const results = downloads.map((download, index) =>
      requests.run(new AbortController().signal, () => {
        order.push(index);
        return download.promise;
      }),
    );
    await vi.advanceTimersByTimeAsync(0);
    expect(order).toEqual([0, 1, 2, 3]);
    downloads[1].resolve('second');
    await vi.advanceTimersByTimeAsync(0);
    expect(order).toEqual([0, 1, 2, 3, 4]);
    downloads[3].resolve('fourth');
    await vi.advanceTimersByTimeAsync(0);
    expect(order).toEqual([0, 1, 2, 3, 4, 5]);
    downloads.forEach((download) => download.resolve('complete'));
    await expect(Promise.all(results)).resolves.toEqual([
      'complete',
      'second',
      'complete',
      'fourth',
      'complete',
      'complete',
    ]);
  });

  it('removes cancelled queued work and rejects already-aborted signals without downloading', async () => {
    const active = Array.from({ length: 4 }, () => deferred());
    const activeResults = active.map((download) =>
      requests.run(new AbortController().signal, () => download.promise),
    );
    const controller = new AbortController();
    const cancelledRequest = vi.fn(async () => 'cancelled');
    const cancelled = requests
      .run(controller.signal, cancelledRequest)
      .catch((error: unknown) => error);
    const nextRequest = vi.fn(async () => 'next');
    const next = requests.run(new AbortController().signal, nextRequest);
    controller.abort();
    await expect(cancelled).resolves.toMatchObject({ name: 'AbortError' });
    await expect(
      requests.run(controller.signal, cancelledRequest),
    ).rejects.toMatchObject({ name: 'AbortError' });
    active[0].resolve('released');
    await vi.advanceTimersByTimeAsync(0);
    expect(cancelledRequest).not.toHaveBeenCalled();
    expect(nextRequest).toHaveBeenCalledOnce();
    await expect(next).resolves.toBe('next');
    active.forEach((download) => download.resolve('complete'));
    await Promise.all(activeResults);
  });

  it('aborts active transport but holds its slot until it settles', async () => {
    const active = Array.from({ length: 4 }, () => deferred());
    const controller = new AbortController();
    let transportSignal: AbortSignal | undefined;
    const cancelled = requests
      .run(controller.signal, (signal) => {
        transportSignal = signal;
        return active[0].promise;
      })
      .catch((error: unknown) => error);
    const others = active
      .slice(1)
      .map((download) =>
        requests.run(new AbortController().signal, () => download.promise),
      );
    const nextRequest = vi.fn(async () => 'next');
    const next = requests.run(new AbortController().signal, nextRequest);
    await vi.advanceTimersByTimeAsync(0);
    controller.abort();
    expect(transportSignal?.aborted).toBe(true);
    await expect(cancelled).resolves.toMatchObject({ name: 'AbortError' });
    await vi.advanceTimersByTimeAsync(0);
    expect(nextRequest).not.toHaveBeenCalled();
    active[0].resolve('transport settled');
    await vi.advanceTimersByTimeAsync(0);
    expect(nextRequest).toHaveBeenCalledOnce();
    active.forEach((download) => download.resolve('complete'));
    await Promise.all([...others, next]);
  });

  it('limits starts to 48 in a rolling minute and resumes only as earlier starts expire', async () => {
    const request = vi.fn(async () => 'system');
    const enqueue = (count: number) =>
      Array.from({ length: count }, () =>
        requests.run(new AbortController().signal, request),
      );
    await Promise.all(enqueue(24));
    expect(request).toHaveBeenCalledTimes(24);
    await vi.advanceTimersByTimeAsync(30_000);
    const second = enqueue(28);
    await vi.advanceTimersByTimeAsync(0);
    expect(request).toHaveBeenCalledTimes(48);
    expect(vi.getTimerCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(request).toHaveBeenCalledTimes(48);
    await vi.advanceTimersByTimeAsync(1);
    await Promise.all(second);
    expect(request).toHaveBeenCalledTimes(52);
    const third = enqueue(24);
    await vi.advanceTimersByTimeAsync(0);
    expect(request).toHaveBeenCalledTimes(72);
    await vi.advanceTimersByTimeAsync(29_999);
    expect(request).toHaveBeenCalledTimes(72);
    await vi.advanceTimersByTimeAsync(1);
    await Promise.all(third);
    expect(request).toHaveBeenCalledTimes(76);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears the rate-limit timer when the final queued request is cancelled', async () => {
    await Promise.all(
      Array.from({ length: 48 }, () =>
        requests.run(new AbortController().signal, async () => 'system'),
      ),
    );
    const controller = new AbortController();
    const download = vi.fn(async () => 'never');
    const queued = requests
      .run(controller.signal, download)
      .catch((error: unknown) => error);
    expect(vi.getTimerCount()).toBe(1);
    controller.abort();
    await expect(queued).resolves.toMatchObject({ name: 'AbortError' });
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(download).not.toHaveBeenCalled();
  });

  it('disposes queued and active work and never starts new requests after late completions', async () => {
    const active = Array.from({ length: 4 }, () => deferred());
    const signals: AbortSignal[] = [];
    const results = active.map((download) =>
      requests
        .run(new AbortController().signal, (signal) => {
          signals.push(signal);
          return download.promise;
        })
        .catch((error: unknown) => error),
    );
    const queuedDownload = vi.fn(async () => 'never');
    const queued = requests
      .run(new AbortController().signal, queuedDownload)
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(0);
    requests.dispose();
    requests.dispose();
    expect(signals).toHaveLength(4);
    expect(signals.every((signal) => signal.aborted)).toBe(true);
    for (const result of [...results, queued]) {
      await expect(result).resolves.toMatchObject({ name: 'AbortError' });
    }
    await expect(
      requests.run(new AbortController().signal, queuedDownload),
    ).rejects.toMatchObject({ name: 'AbortError' });
    active.forEach((download) => download.resolve('late completion'));
    await vi.advanceTimersByTimeAsync(120_000);
    expect(queuedDownload).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('disposes a rate-limited queue without leaving a timer', async () => {
    await Promise.all(
      Array.from({ length: 48 }, () =>
        requests.run(new AbortController().signal, async () => 'system'),
      ),
    );
    const download = vi.fn(async () => 'never');
    const queued = requests
      .run(new AbortController().signal, download)
      .catch((error: unknown) => error);
    expect(vi.getTimerCount()).toBe(1);
    requests.dispose();
    await expect(queued).resolves.toMatchObject({ name: 'AbortError' });
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(download).not.toHaveBeenCalled();
  });

  it('releases capacity after rejected and synchronously thrown requests', async () => {
    const failure = new Error('offline');
    const results = Array.from({ length: 8 }, (_, index) =>
      requests
        .run(new AbortController().signal, () => {
          if (index % 2) throw failure;
          return Promise.reject(failure);
        })
        .catch((error: unknown) => error),
    );
    await expect(Promise.all(results)).resolves.toEqual(Array(8).fill(failure));
    await expect(
      requests.run(new AbortController().signal, async () => 'recovered'),
    ).resolves.toBe('recovered');
  });
});
