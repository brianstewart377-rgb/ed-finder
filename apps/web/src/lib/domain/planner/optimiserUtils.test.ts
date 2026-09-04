import { describe, expect, it } from 'vitest';
import { candidatePlacementsToPreviewPlacements } from './optimiserUtils';

describe('optimiser placement normalisation', () => {
  it('converts and resequences without mutating input', () => {
    const input = [
      {
        facility_template_id: 'support-second',
        local_body_id: undefined,
        is_primary_port: true,
        build_order: 20,
      },
      {
        facility_template_id: 'port-first',
        local_body_id: 'body1',
        is_primary_port: true,
        build_order: 10,
      },
      {
        facility_template_id: 'support-third',
        local_body_id: null,
        is_primary_port: false,
        build_order: 30,
      },
    ];
    const before = structuredClone(input);

    const output = candidatePlacementsToPreviewPlacements(input);

    expect(input).toEqual(before);
    expect(output).toEqual([
      {
        facility_template_id: 'port-first',
        local_body_id: 'body1',
        is_primary_port: true,
        build_order: 1,
      },
      {
        facility_template_id: 'support-second',
        local_body_id: null,
        is_primary_port: false,
        build_order: 2,
      },
      {
        facility_template_id: 'support-third',
        local_body_id: null,
        is_primary_port: false,
        build_order: 3,
      },
    ]);
    expect(output[0]).not.toBe(input[1]);
  });
});
