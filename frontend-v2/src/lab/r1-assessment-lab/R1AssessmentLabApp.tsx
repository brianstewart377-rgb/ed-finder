import { useState } from 'react';

import { R1_ASSESSMENT_FIXTURES, R1_ASSESSMENT_TEMPLATE } from '@/lab/r1-assessment-lab/core/fixtures';
import { evaluateAssessment } from '@/lab/r1-assessment-lab/core/evaluateAssessment';
import type {
  AssessmentEvaluationResult,
  AssessmentLens,
  CarrierMode,
  ScenarioAssessment,
} from '@/lab/r1-assessment-lab/core/types';

const FIXTURE_OPTIONS = [
  'compact_sufficient_case',
  'incomplete_evidence_case',
  'contradictory_allocation_case',
  'fake_flexibility_case',
  'remote_materials_carrier_case',
] as const;

const LENS_KIND_OPTIONS = ['role', 'question'] as const;
const ROLE_OPTIONS = ['expedition-lead', 'logistics-reviewer'] as const;
const QUESTION_OPTIONS = ['baseline-assessment', 'carrier-sensitivity-check'] as const;
const CARRIER_MODE_OPTIONS = ['no_carrier', 'carrier_available', 'compare_both'] as const;

type FixtureOption = typeof FIXTURE_OPTIONS[number];
type LensKindOption = typeof LENS_KIND_OPTIONS[number];
type RoleOption = typeof ROLE_OPTIONS[number];
type QuestionOption = typeof QUESTION_OPTIONS[number];

function lensValueFor(kind: LensKindOption): RoleOption | QuestionOption {
  return kind === 'role' ? 'expedition-lead' : 'baseline-assessment';
}

function buildLens(kind: LensKindOption, value: string): AssessmentLens {
  if (kind === 'role') {
    return { kind: 'role', roleId: value };
  }
  return { kind: 'question', questionId: value };
}

function renderConditions(scenario: ScenarioAssessment) {
  if (scenario.conditions.length === 0) {
    return <p>No structured conditions.</p>;
  }

  return (
    <ul>
      {scenario.conditions.map((condition) => (
        <li key={condition.id}>
          <div><code>{condition.id}</code></div>
          <div>{condition.summary}</div>
          <div>blocking: <code>{String(condition.blocking)}</code></div>
        </li>
      ))}
    </ul>
  );
}

function renderRequirementTrace(scenario: ScenarioAssessment) {
  return (
    <table>
      <thead>
        <tr>
          <th scope="col">requirementId</th>
          <th scope="col">outcome</th>
          <th scope="col">matchedEvidenceIds</th>
          <th scope="col">missingEvidenceIds</th>
          <th scope="col">contradictoryEvidenceIds</th>
          <th scope="col">carrierLogisticsAffected</th>
        </tr>
      </thead>
      <tbody>
        {scenario.requirementResults.map((requirement) => (
          <tr key={requirement.requirementId}>
            <td><code>{requirement.requirementId}</code></td>
            <td><code>{requirement.outcome}</code></td>
            <td><code>{requirement.matchedEvidenceIds.join(', ') || '[]'}</code></td>
            <td><code>{requirement.missingEvidenceIds.join(', ') || '[]'}</code></td>
            <td><code>{requirement.contradictoryEvidenceIds.join(', ') || '[]'}</code></td>
            <td><code>{String(requirement.carrierLogisticsAffected)}</code></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderFrozenEvidence(scenario: ScenarioAssessment) {
  return (
    <table>
      <thead>
        <tr>
          <th scope="col">id</th>
          <th scope="col">factKey</th>
          <th scope="col">availability</th>
          <th scope="col">fixtureId</th>
          <th scope="col">fixtureRevision</th>
        </tr>
      </thead>
      <tbody>
        {scenario.frozenEvidence.map((evidence) => (
          <tr key={evidence.id}>
            <td><code>{evidence.id}</code></td>
            <td><code>{evidence.factKey}</code></td>
            <td><code>{evidence.availability}</code></td>
            <td><code>{evidence.provenance.fixtureId}</code></td>
            <td><code>{evidence.provenance.fixtureRevision}</code></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ScenarioResultSection({ scenario }: { scenario: ScenarioAssessment }) {
  return (
    <section data-testid={`scenario-${scenario.carrierMode}`}>
      <h3><code>{scenario.carrierMode}</code></h3>

      <h4>Assessment state</h4>
      <p data-testid={`scenario-state-${scenario.carrierMode}`}><code>{scenario.state}</code></p>

      <h4>Structured conditions</h4>
      {renderConditions(scenario)}

      <h4>Requirement trace</h4>
      {renderRequirementTrace(scenario)}

      <h4>Frozen evidence and provenance</h4>
      {renderFrozenEvidence(scenario)}
    </section>
  );
}

export default function R1AssessmentLabApp() {
  const [fixtureId, setFixtureId] = useState<FixtureOption>('compact_sufficient_case');
  const [lensKind, setLensKind] = useState<LensKindOption>('role');
  const [lensValue, setLensValue] = useState<RoleOption | QuestionOption>('expedition-lead');
  const [carrierMode, setCarrierMode] = useState<CarrierMode>('no_carrier');

  const selectedLens = buildLens(lensKind, lensValue);
  const result: AssessmentEvaluationResult = evaluateAssessment({
    fixture: R1_ASSESSMENT_FIXTURES[fixtureId],
    template: R1_ASSESSMENT_TEMPLATE,
    lens: selectedLens,
    carrierMode,
  });

  const selectedLensContext = selectedLens.kind === 'role'
    ? `role / ${selectedLens.roleId}`
    : `question / ${selectedLens.questionId}`;

  const lensOptions = lensKind === 'role' ? ROLE_OPTIONS : QUESTION_OPTIONS;

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
          <p>R1 Lab — DEV-only fixture-backed reconstruction.</p>
          <p>R1 Lab — historic evaluator recovery is not claimed.</p>
          <p>R1 Lab — no production scoring or live system advice.</p>
          <p>R1 Lab — Lens context only: changing it does not alter fixture outcomes, requirement outcomes, conditions, assessment state, or ordering in Stage 3B.</p>
          <p>R1 Lab — Lens labels are local presentation context, not rebuilt role or question semantics.</p>
          <p>Template: r1_assessment_programme / core_assessment_template / r1-contract-v1 (fixed for Stage 3B)</p>

          <div>
            <label htmlFor="r1-fixture-select">Fixture</label>{' '}
            <select
              id="r1-fixture-select"
              value={fixtureId}
              onChange={(event) => setFixtureId(event.currentTarget.value as FixtureOption)}
            >
              {FIXTURE_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="r1-lens-kind-select">Lens kind</label>{' '}
            <select
              id="r1-lens-kind-select"
              value={lensKind}
              onChange={(event) => {
                const nextKind = event.currentTarget.value as LensKindOption;
                setLensKind(nextKind);
                setLensValue(lensValueFor(nextKind));
              }}
            >
              {LENS_KIND_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="r1-lens-value-select">Lens value</label>{' '}
            <select
              id="r1-lens-value-select"
              value={lensValue}
              onChange={(event) => setLensValue(event.currentTarget.value as RoleOption | QuestionOption)}
            >
              {lensOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="r1-carrier-mode-select">Carrier mode</label>{' '}
            <select
              id="r1-carrier-mode-select"
              value={carrierMode}
              onChange={(event) => setCarrierMode(event.currentTarget.value as CarrierMode)}
            >
              {CARRIER_MODE_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>

          <p data-testid="selected-lens-context">Selected lens context: {selectedLensContext}</p>

          {carrierMode === 'compare_both' ? (
            <section>
              <h2>Carrier scenario comparison</h2>
              {result.scenarioResults.map((scenario) => (
                <ScenarioResultSection key={scenario.carrierMode} scenario={scenario} />
              ))}
            </section>
          ) : (
            result.scenarioResults.map((scenario) => (
              <ScenarioResultSection key={scenario.carrierMode} scenario={scenario} />
            ))
          )}
        </div>
      </div>
    </main>
  );
}
