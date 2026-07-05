import { Newspaper } from 'lucide-react';
import { useEliteNewsFeed } from './useEliteNewsFeed';

export function EliteNewsBanner() {
  const { items, status, stale } = useEliteNewsFeed({ limit: 8 });
  const haveItems = items.length > 0;
  const feedState = status === 'live'
    ? (stale ? 'cached headlines' : 'latest headlines')
    : status === 'offline'
      ? 'offline'
      : 'loading';

  return (
    <div
      data-testid="elite-news-banner"
      className="fixed bottom-0 left-0 right-0 z-20 pointer-events-none"
    >
      <div className="mx-auto max-w-[1840px] px-4 pb-3 pointer-events-auto">
        <div
          className="panel flex items-stretch overflow-hidden"
          style={{ borderRadius: '20px' }}
        >
          <div
            className="flex items-center gap-2 px-4 shrink-0 border-r border-border/70 rounded-l-[20px]"
            style={{
              background: 'linear-gradient(180deg, rgba(255,122,20,0.18), rgba(255,122,20,0.04))',
            }}
          >
            <span className="grid place-items-center w-6 h-6 rounded-full bg-orange/15 text-orange-lt">
              <Newspaper size={13} strokeWidth={2.2} />
            </span>
            <div className="flex flex-col leading-none">
              <span className="font-display text-[11px] tracking-[0.18em] text-orange font-bold uppercase">
                Elite News
              </span>
              <span className="font-mono text-[8px] tracking-[0.22em] text-silver-dk uppercase mt-0.5">
                {feedState}
              </span>
            </div>
          </div>

          <div className="flex-1 overflow-hidden relative group">
            {haveItems ? (
              <div className="whitespace-nowrap py-2 animate-marquee group-hover:[animation-play-state:paused]">
                {[...items, ...items].map((item, index) => (
                  <a
                    key={`${item.url}-${index}`}
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 mx-3 align-middle rounded-chunk-sm px-1 py-0.5 transition-colors hover:bg-orange/10"
                    data-testid={index < items.length ? `elite-news-link-${index}` : undefined}
                    title={item.title}
                  >
                    <span
                      className={[
                        'font-display text-[9.5px] tracking-[0.14em] uppercase font-bold px-2 py-0.5 rounded-full border',
                        item.source === 'galnet'
                          ? 'text-sky-200 border-sky-300/35 bg-sky-300/10'
                          : 'text-orange-lt border-orange/35 bg-orange/10',
                      ].join(' ')}
                    >
                      {item.source === 'galnet' ? 'Galnet' : 'News'}
                    </span>
                    <span className="font-mono text-[11px] text-silver hover:text-white">
                      {item.title}
                    </span>
                  </a>
                ))}
              </div>
            ) : (
              <div className="py-2 px-4 font-mono text-[11px] text-silver-dk italic">
                {status === 'offline'
                  ? 'Official Elite Dangerous headlines unavailable'
                  : 'Loading official Elite Dangerous headlines'}
              </div>
            )}
          </div>

          <div className="hidden md:flex items-center gap-2 px-4 shrink-0 border-l border-border/70 bg-bg3/40 rounded-r-[20px]">
            <span className="font-mono text-[10px] tracking-widest text-silver-dk uppercase">
              {items.length} headlines
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
