/** Deterministic compatibility fixtures transcribed from the React store tests. */
export const legacyPersistenceFixtures = {
  pinnedBareArray: JSON.stringify([
    {
      id64: 12345,
      name: 'Test System',
      x: 0,
      y: 0,
      z: 0,
      population: 0,
      is_colonised: false,
      economy: 'Tourism',
      pinned_at: '2026-07-07T00:00:00Z',
    },
  ]),
  fcRoute: JSON.stringify({
    waypoints: [
      { id: 'wp-sync', name: 'Achenar', x: 67, y: 12, z: -33, id64: 123 },
    ],
    config: {
      jump_range_ly: 420,
      cargo_t: 25000,
      tritium_per_jump: 50,
      tritium_price_cr: 50000,
    },
  }),
  colonyProjectsV1: JSON.stringify({
    state: {
      projects: [
        {
          id: 'legacy-project',
          system_id64: 123,
          system_name: 'Legacy',
          project_name: 'Legacy project',
          build_plan_placements: [],
          selected_body_assignments: {},
          target_archetype: 'refinery_industrial',
          notes: '',
          status: 'validated',
          created_at: '2026-05-01T00:00:00.000Z',
          updated_at: '2026-05-01T00:00:00.000Z',
          archived_at: null,
        },
      ],
    },
    version: 1,
  }),
} as const;
