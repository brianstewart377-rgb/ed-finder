import type { SimulateBuildResponse } from '@/types/api';
import { Message, Metric } from './components/ui';
import { confidenceLabel, titleCase } from './utils/formatters';
import { confidenceTone, complexityTone } from './utils/toneHelpers';
import { ObservedVsPredictedPanel } from './panels/ObservedVsPredictedPanel';
import { DataConfidencePanel } from './panels/DataConfidencePanel';
import { MechanicsTracePanel } from './panels/MechanicsTracePanel';
import { EconomyBars, EconomyStackPanel, InheritedEconomyPanel, PortEconomyPanel } from './panels/EconomyPanels';
import { TopologyPanel } from './panels/TopologyPanel';
import { CpRepairPanel, CpSummary, CpTimelinePanel } from './panels/CpPanels';
import { PortServicePanel, ServicesPanel } from './panels/ServicesPanels';
import { LinkSummary } from './panels/LinkSummary';

export function SimulationResult({ result }: { result: SimulateBuildResponse }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <Metric label="Final score" value={Math.round(result.final_score)} tone="orange" />
        <Metric label="Build" value={titleCase(result.build_complexity)} tone={complexityTone(result.build_complexity)} />
        <Metric label="Confidence" value={confidenceLabel(result.confidence)} tone={confidenceTone(result.confidence)} />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Metric label="Composition" value={Math.round(result.composition_score)} />
        <Metric label="Buildability" value={Math.round(result.buildability_score)} />
      </div>

      <DataConfidencePanel result={result} />
      <ObservedVsPredictedPanel summary={result.observation_summary} diffs={result.prediction_observation_diffs} />
      <EconomyBars composition={result.economy_composition} order={result.economy_order} />
      <EconomyStackPanel stack={result.economy_stack} />
      <PortEconomyPanel states={result.port_economy_states} ledger={result.influence_ledger} />
      <InheritedEconomyPanel profiles={result.inherited_economies} />
      <TopologyPanel topology={result.topology} />
      <CpSummary cp={result.cp} />
      <CpRepairPanel suggestions={result.cp_repair_suggestions} />
      <CpTimelinePanel timeline={result.cp_timeline} />
      <ServicesPanel services={result.services} />
      <PortServicePanel states={result.port_service_states} ledger={result.service_unlock_ledger} />

      <div className="grid gap-2">
        {result.strengths.length > 0 && <Message title="Why this works" tone="good" items={result.strengths} />}
        {result.warnings.length > 0 && <Message title="Warnings" tone="warn" items={result.warnings} />}
        {result.recommendations.length > 0 && <Message title="Next steps" tone="info" items={result.recommendations} />}
      </div>

      <LinkSummary result={result} />
      <MechanicsTracePanel trace={result.mechanics_trace} />
    </div>
  );
}
