import { EconomyJigsawChip } from '@/components/EconomyJigsawChip';
import { economyColor, economySoftColor } from '@/features/colony-planner/economyVisuals';

const CHIP_VARIANTS = [
  {
    label: 'Refinery / Industrial Megacomplex',
    primaryEconomy: 'Refinery',
    secondaryEconomy: 'Industrial',
    suffix: 'Megacomplex',
  },
  {
    label: 'Agriculture / Terraforming Colony',
    primaryEconomy: 'Agriculture',
    secondaryEconomy: 'Terraforming',
    suffix: 'Colony',
  },
  {
    label: 'High Tech / Tourism Prestige Colony',
    primaryEconomy: 'HighTech',
    secondaryEconomy: 'Tourism',
    suffix: 'Prestige Colony',
  },
  {
    label: 'Extraction / Refinery Mining Hub',
    primaryEconomy: 'Extraction',
    secondaryEconomy: 'Refinery',
    suffix: 'Mining Hub',
  },
  {
    label: 'Military / Industrial Complex',
    primaryEconomy: 'Military',
    secondaryEconomy: 'Industrial',
    suffix: 'Complex',
  },
] as const;

export function ChipPreview() {
  return (
    <section
      data-testid="chip-preview"
      className="panel-thin mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-8"
    >
      <header className="space-y-2">
        <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-cyan-200/70">
          Isolated chip preview
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-[0.08em] text-orange-lt">
          Jigsaw economy chip
        </h1>
        <p className="max-w-2xl text-sm text-silver">
          This route strips away live search data and shows only the paired-economy chip geometry,
          so you can judge the tab/notch silhouette in isolation.
        </p>
      </header>

      <div className="grid gap-4">
        {CHIP_VARIANTS.map((variant) => (
          <div
            key={variant.label}
            className="rounded-2xl border border-border/80 bg-bg3/55 px-5 py-5 shadow-[0_18px_48px_-28px_rgba(0,0,0,0.92)]"
          >
            <div className="flex flex-wrap items-center gap-4">
              <EconomyJigsawChip
                label={variant.label}
                title={variant.label}
                primaryEconomy={variant.primaryEconomy}
                secondaryEconomy={variant.secondaryEconomy}
                suffix={variant.suffix}
                primaryColor={economyColor(variant.primaryEconomy)}
                secondaryColor={economyColor(variant.secondaryEconomy)}
                primarySoft={economySoftColor(variant.primaryEconomy)}
                secondarySoft={economySoftColor(variant.secondaryEconomy)}
                testIdPrefix={`chip-preview-${variant.primaryEconomy.toLowerCase()}-${variant.secondaryEconomy.toLowerCase()}`}
              />
              <span className="font-mono text-[11px] tracking-[0.14em] text-silver-dk">
                {variant.label}
              </span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
