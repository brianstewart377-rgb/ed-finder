import { describe, expect, it } from 'vitest';
import type { SimulateBuildResponse } from './types';
import {
  filterComparisonsByStatus,
  formatComparisonValue,
  previewResultFingerprint,
  validationInputProjection,
} from './validationUtils';

function validationPreview(): SimulateBuildResponse {
  return {
    final_score: 80,
    confidence: 0.7,
    cp: {
      yellow_cp_final: 1,
      green_cp_final: 2,
      yellow_cp_generated: 3,
      green_cp_generated: 4,
      yellow_cp_spent: 5,
      green_cp_spent: 6,
      t2_ports: 7,
      t3_ports: 8,
      warnings: ['baseline warning'],
    },
    cp_timeline: [],
    cp_repair_suggestions: [],
    economy_composition: { industrial: 1 },
    economy_order: ['industrial'],
    services: {
      market: { status: 'active' },
    },
    port_service_states: [
      {
        active_services: { market: {} },
        locked_services: { shipyard: {} },
        unknown_services: { vista_genomics: {} },
      },
    ],
  };
}

type BackendReadChange = [string, (preview: SimulateBuildResponse) => void];

const backendReadChanges: BackendReadChange[] = [
  [
    'final_score',
    (preview) => {
      preview.final_score += 1;
    },
  ],
  [
    'confidence',
    (preview) => {
      preview.confidence += 0.01;
    },
  ],
  [
    'cp.yellow_cp_final',
    (preview) => {
      preview.cp.yellow_cp_final += 1;
    },
  ],
  [
    'cp.green_cp_final',
    (preview) => {
      preview.cp.green_cp_final += 1;
    },
  ],
  [
    'cp.yellow_cp_generated',
    (preview) => {
      preview.cp.yellow_cp_generated += 1;
    },
  ],
  [
    'cp.green_cp_generated',
    (preview) => {
      preview.cp.green_cp_generated += 1;
    },
  ],
  [
    'cp.yellow_cp_spent',
    (preview) => {
      preview.cp.yellow_cp_spent += 1;
    },
  ],
  [
    'cp.green_cp_spent',
    (preview) => {
      preview.cp.green_cp_spent += 1;
    },
  ],
  [
    'cp.t2_ports',
    (preview) => {
      preview.cp.t2_ports += 1;
    },
  ],
  [
    'cp.t3_ports',
    (preview) => {
      preview.cp.t3_ports += 1;
    },
  ],
  [
    'cp.warnings',
    (preview) => {
      preview.cp.warnings.push('changed warning');
    },
  ],
  [
    'economy_composition',
    (preview) => {
      preview.economy_composition.industrial += 1;
    },
  ],
  [
    'economy_order',
    (preview) => {
      preview.economy_order[0] = 'tourism';
    },
  ],
  [
    'services status',
    (preview) => {
      const market = preview.services.market;
      if (market) market.status = 'locked';
    },
  ],
  [
    'port_service_states.active_services',
    (preview) => {
      preview.port_service_states[0].active_services.repair = {};
    },
  ],
  [
    'port_service_states.locked_services',
    (preview) => {
      preview.port_service_states[0].locked_services.refuel = {};
    },
  ],
  [
    'port_service_states.unknown_services',
    (preview) => {
      preview.port_service_states[0].unknown_services.bartender = {};
    },
  ],
];

describe('validation cache input', () => {
  it.each(backendReadChanges)(
    'changes the fingerprint when %s changes',
    (_field, change) => {
      const before = validationPreview();
      const after = structuredClone(before);
      change(after);

      expect(previewResultFingerprint(after)).not.toBe(
        previewResultFingerprint(before),
      );
    },
  );

  it('uses the same complete projection for the request and fingerprint', () => {
    const preview = validationPreview();

    expect(previewResultFingerprint(preview)).toBe(
      JSON.stringify(validationInputProjection(preview)),
    );
    expect(validationInputProjection(preview)).toMatchObject({
      cp: {
        yellow_cp_generated: 3,
        green_cp_generated: 4,
        yellow_cp_spent: 5,
        green_cp_spent: 6,
      },
      port_service_states: [
        {
          active_services: { market: true },
          locked_services: { shipyard: true },
          unknown_services: { vista_genomics: true },
        },
      ],
    });
  });

  it('normalises ordering and applies active then locked service precedence', () => {
    const first = validationPreview();
    first.economy_composition = { tourism: 2, industrial: 1 };
    first.services = {
      shipyard: { status: 'locked' },
      market: { status: 'active' },
    };
    first.port_service_states = [
      {
        active_services: { market: {}, repair: {} },
        locked_services: { market: {}, shipyard: {} },
        unknown_services: { repair: {}, shipyard: {}, vista_genomics: {} },
      },
    ];

    const second = structuredClone(first);
    second.economy_composition = { industrial: 1, tourism: 2 };
    second.services = {
      market: { status: 'active' },
      shipyard: { status: 'locked' },
    };

    expect(previewResultFingerprint(first)).toBe(
      previewResultFingerprint(second),
    );
    expect(validationInputProjection(first)).toMatchObject({
      port_service_states: [
        {
          active_services: { market: true, repair: true },
          locked_services: { shipyard: true },
          unknown_services: { vista_genomics: true },
        },
      ],
    });
    expect(previewResultFingerprint(null)).toBeNull();
  });
});

describe('validation display helpers', () => {
  it('formats scalar, structured, and absent comparison values', () => {
    expect(formatComparisonValue(undefined)).toBe('—');
    expect(formatComparisonValue(null)).toBe('—');
    expect(formatComparisonValue('active')).toBe('active');
    expect(formatComparisonValue(12)).toBe('12');
    expect(formatComparisonValue(false)).toBe('false');
    expect(formatComparisonValue({ service: 'market' })).toBe(
      '{"service":"market"}',
    );
  });

  it('filters exact statuses and preserves the unfiltered array', () => {
    const comparisons = [
      { status: 'confirmed' },
      { status: 'future_backend_status' },
    ];

    expect(filterComparisonsByStatus(comparisons, null)).toBe(comparisons);
    expect(filterComparisonsByStatus(comparisons, '')).toBe(comparisons);
    expect(filterComparisonsByStatus(comparisons, 'confirmed')).toEqual([
      comparisons[0],
    ]);
  });
});
