export function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="premium-subpanel px-4 py-12 text-center">
      <h2 className="font-display text-sm tracking-[0.12em] text-text">{title}</h2>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-silver-dk">{body}</p>
    </div>
  );
}
