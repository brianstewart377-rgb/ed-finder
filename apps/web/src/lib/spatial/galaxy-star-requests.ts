/** Bound both simultaneous cell downloads and the map route's 60/minute budget. */
export class GalaxyStarRequests {
  private active = 0;
  private starts: number[] = [];
  private queue: { start: () => void; cancel: () => void }[] = [];
  private jobs = new Set<{ cancel: () => void }>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private disposed = false;

  run<T>(
    signal: AbortSignal,
    request: (signal: AbortSignal) => Promise<T>,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const controller = new AbortController();
      let cancelled = false;
      const cleanup = () => {
        signal.removeEventListener('abort', job.cancel);
        this.jobs.delete(job);
      };
      const job = {
        cancel: () => {
          if (cancelled) return;
          cancelled = true;
          this.queue = this.queue.filter((queued) => queued !== job);
          controller.abort();
          cleanup();
          reject(new DOMException('Cell request cancelled', 'AbortError'));
          this.drain();
        },
        start: () => {
          this.active += 1;
          this.starts.push(Date.now());
          void Promise.resolve()
            .then(() => {
              if (controller.signal.aborted) {
                throw new DOMException('Cell request cancelled', 'AbortError');
              }
              return request(controller.signal);
            })
            .then(resolve, reject)
            .finally(() => {
              cleanup();
              // An aborted transport may take time to settle. Keep its slot
              // occupied until then so cancellation cannot exceed concurrency.
              this.active -= 1;
              this.drain();
            });
        },
      };
      if (signal.aborted || this.disposed) job.cancel();
      else {
        signal.addEventListener('abort', job.cancel, { once: true });
        this.jobs.add(job);
        this.queue.push(job);
        this.drain();
      }
    });
  }

  private drain(): void {
    clearTimeout(this.timer);
    this.timer = undefined;
    if (this.disposed) return;
    this.starts = this.starts.filter((start) => Date.now() - start < 60_000);
    while (this.queue.length && this.active < 4 && this.starts.length < 48) {
      this.queue.shift()!.start();
    }
    if (this.queue.length && this.starts.length >= 48) {
      this.timer = setTimeout(
        () => this.drain(),
        60_001 - (Date.now() - this.starts[0]),
      );
    }
  }

  dispose(): void {
    this.disposed = true;
    clearTimeout(this.timer);
    this.timer = undefined;
    for (const job of [...this.jobs]) job.cancel();
  }
}
