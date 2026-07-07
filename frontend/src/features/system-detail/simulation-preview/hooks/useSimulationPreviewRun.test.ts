import { describe, expect, it } from 'vitest';
import type { SimulateBuildPlacement } from '@/types/api';
import { previewInputFingerprint } from './useSimulationPreviewRun';

const placements: SimulateBuildPlacement[] = [
  { facility_template_id: 'generic_port_alpha', local_body_id: 'body1', is_primary_port: true, build_order: 2 },
  { facility_template_id: 'agri_support_a', local_body_id: 'body1', is_primary_port: false, build_order: 1 },
];

describe('previewInputFingerprint', () => {
  it('includes system id so identical plans in different systems are distinct', () => {
    const first = previewInputFingerprint(123, 'agriculture_terraforming', placements);
    const second = previewInputFingerprint(456, 'agriculture_terraforming', placements);

    expect(first).not.toBe(second);
    expect(JSON.parse(first)).toMatchObject({ system_id64: 123 });
    expect(JSON.parse(second)).toMatchObject({ system_id64: 456 });
  });
});
