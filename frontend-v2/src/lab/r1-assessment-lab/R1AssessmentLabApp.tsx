export default function R1AssessmentLabApp() {
  return (
    <main className="min-h-screen px-4 py-8 text-slate-100 sm:px-6">
      <div className="mx-auto max-w-3xl rounded-2xl border border-cyan-500/40 bg-slate-950/90 p-6 shadow-2xl shadow-cyan-950/30">
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-300">
            R1 Assessment Laboratory
          </p>
          <h1 className="text-3xl font-semibold text-white">
            DEV only — reconstruction shell
          </h1>
          <ul className="space-y-2 text-sm text-slate-200">
            <li>No production scoring</li>
            <li>No network or persistence</li>
            <li>Assessment engine not yet reconstructed</li>
          </ul>
        </div>
      </div>
    </main>
  );
}
