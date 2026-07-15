import { useMemo } from 'react';
import { MapPin } from 'lucide-react';
import { useExpansionPlanStore, activePlansForSystem } from './expansionPlanStore';

interface ExpansionPlanBadgeProps {
  id64: number;
  onOpenPlan?: (planId: string) => void;
}

export function ExpansionPlanBadge({ id64, onOpenPlan }: ExpansionPlanBadgeProps) {
  const plansRecord = useExpansionPlanStore((state) => state.plans);
  const matches = useMemo(
    () => activePlansForSystem(Object.values(plansRecord), id64),
    [plansRecord, id64],
  );

  if (matches.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {matches.map((plan) => {
        const slot = plan.slots.find((s) => s.system_id64 === id64);
        return (
          <button
            key={plan.id}
            type="button"
            onClick={() => onOpenPlan?.(plan.id)}
            className="flex items-center gap-1 px-2 py-0.5 rounded-full border border-cyan/40 bg-cyan/10 text-cyan text-[10px] font-mono uppercase tracking-wide hover:bg-cyan/20 transition-colors"
            title={slot ? `Role: ${slot.label}` : undefined}
          >
            <MapPin size={10} />
            {plan.plan_name}
          </button>
        );
      })}
    </div>
  );
}
