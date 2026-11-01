import type {
  PlanBodiesV1,
  PlanCatalogueV1,
  PlanEvaluationV1,
  PlanFacilityV1,
  PlanRequestV1,
  PlanStepV1,
  PlanSystemBodyV1,
} from '../../src/lib/api/generated/types.gen';

// S4 is a browser-only slice. Ordinary success responses keep this journey
// independent of database seeds; all displayed budgets come from the intercepted
// evaluation contract, including the picker's evaluation preview.
const systemId = '9007199254740993';
const systemName = 'Planner Reference';
const primaryId = 'coriolis';
const consumerId = 'industrial-installation';
const payerId = 'mining-installation';

function facility(
  id: string,
  name: string,
  fields: Partial<PlanFacilityV1>,
): PlanFacilityV1 {
  return {
    id,
    name,
    category: 'installation',
    tier: 1,
    allowed_location: 'orbital',
    economy: null,
    is_port: false,
    escalating_port_tier: null,
    yellow_cp_cost: 0,
    green_cp_cost: 0,
    yellow_cp_generated: 0,
    green_cp_generated: 0,
    prerequisites: [],
    rule_ids: ['RB-0002'],
    ...fields,
  };
}

const catalogue: PlanCatalogueV1 = {
  rulebook_release: 'browser-contract-v1',
  facilities: [
    facility(primaryId, 'Coriolis Starport', {
      category: 'port',
      tier: 2,
      is_port: true,
      escalating_port_tier: 2,
      yellow_cp_cost: 3,
      green_cp_generated: 1,
    }),
    facility(consumerId, 'Industrial Installation', {
      tier: 2,
      yellow_cp_cost: 1,
      green_cp_generated: 1,
    }),
    facility(payerId, 'Mining Installation', { yellow_cp_generated: 2 }),
    // Raven uses the catalogue's real identifiers; retain the existing journey
    // fixtures above and make these two imported facilities available too.
    facility('coriolis_station', 'Coriolis Starport', {
      category: 'port',
      tier: 2,
      is_port: true,
      escalating_port_tier: 2,
    }),
    facility('orbital_installation_mining_outpost', 'Mining Outpost', {}),
    facility('planetary_port', 'Port', {
      category: 'port',
      is_port: true,
      tier: 3,
      allowed_location: 'surface',
    }),
    facility('surface_settlement_agriculture', 'Agricultural Settlement', {
      category: 'agriculture',
      allowed_location: 'surface',
    }),
    ...Array.from({ length: 12 }, (_, index) =>
      facility(
        `orbital-fixture-${index}`,
        `Research Installation ${index + 1}`,
        {},
      ),
    ),
  ],
};

function body(
  body_id: string,
  name: string,
  fields: Partial<PlanSystemBodyV1>,
): PlanSystemBodyV1 {
  return {
    body_id,
    name,
    direct_parent_body_id: null,
    body_type: 'Rocky body',
    is_main_star: false,
    is_landable: true,
    radius_km: 3200,
    surface_gravity_g: 0.5,
    surface_temperature_k: 240,
    atmosphere: 'No atmosphere',
    terraforming_state: 'Not terraformable',
    volcanism: 'No volcanism',
    distance_from_arrival_ls: 100,
    has_rings: false,
    geological_signals: 0,
    biological_signals: 0,
    signals_complete: true,
    lifecycle_state: 'ACTIVE',
    ...fields,
  };
}

const bodies: PlanBodiesV1 = {
  generation_id: 'planner-browser-generation',
  publication_sequence: '1',
  system_id64: systemId,
  bodies: [
    body('star-a', `${systemName} A`, {
      body_type: 'Star',
      is_main_star: true,
      is_landable: false,
      radius_km: 600000,
    }),
    body('planet-1', `${systemName} A 1`, {
      direct_parent_body_id: 'star-a',
      has_rings: true,
      geological_signals: 2,
    }),
    body('cluster-2', `${systemName} A A Belt Cluster 2`, {
      body_type: 'Belt Cluster',
      direct_parent_body_id: 'star-a',
      is_landable: false,
    }),
    body('cluster-1', `${systemName} A A Belt Cluster 1`, {
      body_type: 'Belt Cluster',
      direct_parent_body_id: 'star-a',
      is_landable: false,
    }),
  ],
  belts: [
    {
      belt_id: 'belt-a',
      lifecycle_state: 'ACTIVE',
      name: `${systemName} A A Belt`,
      parent_body_id: 'star-a',
      ring_type: 'Rocky',
      reserve: 'Pristine',
      mass_mt: null,
      inner_radius_km: null,
      outer_radius_km: null,
    },
  ],
};

function evaluation(request: PlanRequestV1): PlanEvaluationV1 {
  const ids = request.sites.map((site) => site.facility_id);
  const hasConsumer = ids.includes(consumerId);
  const hasPayer = ids.includes(payerId);
  const funded = hasPayer && ids.indexOf(payerId) < ids.indexOf(consumerId);
  const preview = request.sites.some((site) =>
    site.site_id.startsWith('preview-'),
  );
  const steps = request.sites.map((site): PlanStepV1 => {
    const blocked = !preview && site.facility_id === consumerId && !funded;
    const consumer = site.facility_id === consumerId;
    const payer = site.facility_id === payerId;
    return {
      site_id: site.site_id,
      facility_id: site.facility_id,
      status: site.status,
      view: preview ? 'now' : 'after_plan',
      result: preview ? 'COUNTED' : blocked ? 'BLOCKED' : 'OK',
      counted_port_number: site.facility_id === primaryId ? 1 : null,
      cost_t2: consumer ? 1 : 0,
      cost_t3: 0,
      reward_t2: payer ? 2 : 0,
      reward_t3: consumer ? 1 : 0,
      t2_before: consumer && funded ? 2 : 0,
      t3_before: 0,
      t2_after: payer ? 2 : consumer && funded ? 1 : 0,
      t3_after: consumer && funded ? 1 : 0,
      reasons: blocked ? ['Not enough Tier 2 points before this step.'] : [],
      rule_ids: ['RB-0002'],
      payers: blocked ? [payerId] : [],
    };
  });
  return {
    rulebook_release: catalogue.rulebook_release,
    system_id64: request.system_id64,
    now: { t2: 0, t3: 0 },
    after_plan: {
      t2: hasConsumer && funded ? 1 : hasPayer ? 2 : 0,
      t3: hasConsumer && funded ? 1 : 0,
    },
    next_port_cost: { t2: 3, t3: 6 },
    economies: { now: [], after_plan: [], notes: [] },
    steps,
    plan_checks: [],
    summary: {
      OK: steps.filter((step) => step.result === 'OK').length,
      BLOCKED: steps.filter((step) => step.result === 'BLOCKED').length,
      NEEDS_INFO: 0,
      COUNTED: preview ? steps.length : 0,
      IGNORED: 0,
    },
    explanations: {
      'RB-0002': {
        id: 'RB-0002',
        title: 'Construction points',
        status: 'confirmed',
        statement: 'Earlier installations provide points for later builds.',
        quote: 'Tier 1 facilities generate Tier 2 points.',
        page: 4,
      },
    },
  };
}

function installApiFixtures(): void {
  cy.intercept('GET', '/api/v1/auth/session', {
    authenticated: false,
    user: null,
    owner_claim_available: false,
  });
  cy.intercept('GET', '/api/health', {
    status: 'ok',
    database: 'connected',
    version: 'test',
    build_sha: 'planner-browser-fixture',
  });
  cy.intercept('GET', '/api/v1/generation', {
    generation_id: bodies.generation_id,
    generation_key: 'planner-browser',
    publication_sequence: '1',
    published_at: '2026-10-31T00:00:00Z',
  });
  cy.intercept('GET', `/api/v1/systems/${systemId}`, {
    id64: systemId,
    name: systemName,
    x_ly: 0,
    y_ly: 0,
    z_ly: 0,
    source_body_count: 0,
    loaded_body_count: 0,
    lifecycle_state: 'ACTIVE',
    source_updated_at: null,
  });
  for (const resource of ['bodies', 'rings', 'stations']) {
    cy.intercept('GET', `/api/v1/systems/${systemId}/${resource}`, []);
  }
  cy.intercept('GET', `/api/ratings/v4/systems/${systemId}`, {
    derived_generation_id: 'planner-browser-derived',
    publication_sequence: 1,
    canonical_generation_id: bodies.generation_id,
    canonical_publication_sequence: 1,
    scorer_version: '4.0.0',
    mechanics_version: '4.0.0',
    system_id64: systemId,
    ratings: [],
  });
  cy.intercept('GET', '/api/v1/plan/catalogue', catalogue).as('catalogue');
  cy.intercept('GET', `/api/v1/plan/systems/${systemId}/bodies`, bodies).as(
    'planBodies',
  );
  cy.intercept('POST', '/api/v1/plan/evaluate', (request) => {
    const plan = request.body as PlanRequestV1;
    expect(plan.system_id64, 'lossless system id').to.equal(systemId);
    expect(plan.bodies?.map((entry) => entry.body_ref)).not.to.include(
      'cluster-2',
    );
    request.reply(evaluation(plan));
  }).as('evaluate');
}

function addFacility(facilityId: string): void {
  cy.get('[data-plan-body="planet-1"]')
    .find(`button[aria-label="Add a build on ${systemName} A 1"]`)
    .click();
  cy.get('[role="dialog"] [role="tab"]')
    .contains(/^Orbital$/)
    .click();
  cy.get('[role="dialog"] input[type="search"]').type(
    catalogue.facilities.find((entry) => entry.id === facilityId)!.name,
  );
  cy.get(`button[data-facility-id="${facilityId}"]`).click();
}

describe('Colony planner browser-kept main path', () => {
  beforeEach(installApiFixtures);

  for (const [width, height] of [
    [1280, 900],
    [390, 844],
  ] as const) {
    it(`keeps the facility popup inside the viewport without shifting bodies at ${width}px`, () => {
      cy.viewport(width, height);
      cy.visit(`/plan?system=${systemId}`);
      cy.wait(['@catalogue', '@planBodies']);
      const opener = `button[aria-label="Add a build on ${systemName} A 1"]`;
      let bodyTop = 0;
      // Measure inside the body list: content above the pane may finish
      // loading after this point, but the popup must not move the rows.
      const offsetInTree = (body: HTMLElement) =>
        body.getBoundingClientRect().top -
        body.closest('.plan-body-tree')!.getBoundingClientRect().top;
      cy.get('[data-plan-body="planet-1"]').then(($body) => {
        bodyTop = offsetInTree($body[0]);
      });
      cy.get(opener).focus().click();
      cy.get('[role="dialog"]')
        .should('have.attr', 'aria-modal', 'false')
        .and('contain.text', `Add a facility on ${systemName} A 1`)
        .should(($dialog) => {
          const rect = $dialog[0].getBoundingClientRect();
          const document = $dialog[0].ownerDocument;
          const window = document.defaultView!;
          const viewport = window.visualViewport;
          const viewportLeft = viewport?.offsetLeft ?? 0;
          const viewportTop = viewport?.offsetTop ?? 0;
          const viewportWidth = Math.min(
            viewport?.width ?? window.innerWidth,
            document.documentElement.clientWidth,
          );
          const viewportHeight = Math.min(
            viewport?.height ?? window.innerHeight,
            document.documentElement.clientHeight,
          );
          expect(rect.left).to.be.at.least(viewportLeft);
          expect(rect.top).to.be.at.least(viewportTop);
          expect(rect.right).to.be.at.most(
            document.documentElement.clientWidth,
          );
          expect(rect.right).to.be.at.most(viewportLeft + viewportWidth);
          expect(rect.bottom).to.be.at.most(viewportTop + viewportHeight);
          expect($dialog.closest('[data-plan-body]')).to.have.length(0);
          if (viewportWidth < 640) {
            expect(
              Math.abs(
                (rect.left + rect.right) / 2 -
                  (viewportLeft + viewportWidth / 2),
              ),
            ).to.be.lessThan(2);
            expect(
              Math.abs(
                (rect.top + rect.bottom) / 2 -
                  (viewportTop + viewportHeight / 2),
              ),
            ).to.be.lessThan(2);
          }
        });
      cy.focused()
        .should('have.attr', 'role', 'tab')
        .and('have.text', 'Orbital');
      cy.get('[data-plan-body="planet-1"]').should(($body) => {
        expect(offsetInTree($body[0])).to.equal(bodyTop);
      });
      cy.get('[role="dialog"] [role="tabpanel"]').should(($list) => {
        expect($list[0].scrollHeight).to.be.greaterThan($list[0].clientHeight);
        expect(getComputedStyle($list[0]).overflowY).to.equal('auto');
      });
      cy.get('[role="dialog"]')
        .contains(
          'button',
          /Previous facilities|More facilities|Next facilities/,
        )
        .should('not.exist');
      cy.injectAxe();
      cy.checkA11y('[role="dialog"]');
      cy.screenshot(
        `plan/facility-picker-${Cypress.browser.name}-${width}x${height}`,
        {
          capture: 'viewport',
          overwrite: true,
        },
      );
      cy.get('[role="dialog"] [role="tab"]')
        .contains(/^Surface$/)
        .click();
      cy.get('[role="dialog"] button[data-facility-id]').should(
        'have.length',
        2,
      );
      cy.get('[role="dialog"] input[type="search"]').type('Coriolis');
      cy.get('[role="dialog"]').should(
        'contain.text',
        'No matching facilities.',
      );
      cy.get('[role="dialog"] [role="tab"]')
        .contains(/^Orbital$/)
        .click();
      cy.get('[role="dialog"] button[data-facility-id]').should(
        'have.length',
        2,
      );
      cy.press(Cypress.Keyboard.Keys.ESC);
      cy.get('[role="dialog"]').should('not.exist');
      cy.get(opener).should('be.focused');
      cy.get(opener).click();
      cy.contains('button', 'Close picker').click();
      cy.get(opener).should('be.focused');
      cy.get(opener).click();
      cy.get('body').click(2, 2);
      cy.get('[role="dialog"]').should('not.exist');
      cy.get(opener).should('be.focused');
    });

    it(`plans from Inspect, fixes build order and keeps the plan at ${width}px`, () => {
      cy.viewport(width, height);
      cy.visit(`/inspect?system=${systemId}`);
      cy.contains('h1', systemName).should('be.visible');
      cy.contains('a', 'Continue to Plan').focus();
      cy.press(Cypress.Keyboard.Keys.ENTER);
      cy.location('pathname').should('eq', '/plan');
      cy.wait(['@catalogue', '@planBodies']);
      cy.get('[data-plan-body="planet-1"]').should('be.visible');
      cy.get('[data-plan-body="cluster-1"]').should('exist');
      cy.get('[data-plan-body="cluster-2"]').should('not.exist');

      cy.get('[data-plan-body="planet-1"]')
        .find('button[aria-label^="Orbital slots on"]')
        .click();
      cy.get('button[aria-label="Increase orbital slots"]')
        .click()
        .click()
        .click();
      cy.contains('button', 'Done').click();
      cy.get('[data-plan-body="planet-1"]').should('contain.text', '0/3');

      addFacility(primaryId);
      addFacility(consumerId);
      addFacility(payerId);
      cy.get('[aria-live="polite"]').should('contain.text', '1 blocked');
      cy.contains('button', /^Build order \(3\)/)
        .should('have.attr', 'aria-expanded', 'false')
        .click()
        .should('have.attr', 'aria-expanded', 'true');
      cy.get('[data-plan-build-order] [data-plan-site]').should(
        'have.length',
        3,
      );
      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(1)
        .should('contain.text', 'Industrial Installation')
        .and('contain.text', 'Blocked');
      cy.get('[data-plan-summary]')
        .contains('dt', /^Tier 2$/)
        .next('dd')
        .should('have.text', '2');
      cy.get('[data-plan-summary]')
        .contains('dt', 'Next Tier 3 port cost')
        .next('dd')
        .should('have.text', '6 T3');
      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(1)
        .contains('button', 'Why?')
        .focus()
        .click();
      cy.get('[role="dialog"]')
        .should('contain.text', 'Not enough Tier 2 points')
        .and('contain.text', 'Construction points');
      cy.focused().should(($element) => {
        expect($element.closest('[role="dialog"]').length).to.eq(1);
      });
      cy.press(Cypress.Keyboard.Keys.ESC);
      cy.get('[role="dialog"]').should('not.exist');
      cy.focused().should('contain.text', 'Why?');

      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(2)
        .find('button[aria-label^="Move up"]')
        .focus()
        .should('be.focused');
      cy.press(Cypress.Keyboard.Keys.SPACE);
      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(1)
        .should('contain.text', 'Mining Installation');
      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(2)
        .should('contain.text', 'Industrial Installation')
        .and('contain.text', 'OK');
      cy.get('[aria-live="polite"]').should('contain.text', '0 blocked');
      for (const tier of ['Tier 2', 'Tier 3']) {
        cy.get('[data-plan-summary]')
          .contains('dt', new RegExp(`^${tier}$`))
          .next('dd')
          .should('have.text', '1');
      }
      cy.injectAxe();
      cy.checkA11y();
      cy.document().should((document) => {
        expect(document.documentElement.scrollWidth).to.be.at.most(width);
      });
      cy.screenshot(`plan/ordered-${Cypress.browser.name}-${width}x${height}`, {
        capture: 'fullPage',
        overwrite: true,
      });

      cy.reload();
      cy.contains('button', /^Build order \(3\)/).should(
        'have.attr',
        'aria-expanded',
        'true',
      );
      cy.get('[data-plan-build-order]')
        .contains('button', /^Close$/)
        .click();
      cy.get('[data-plan-body="planet-1"]').should('contain.text', '3/3');
      cy.contains('button', /^Build order \(3\)/).click();
      cy.get('[data-plan-build-order] [data-plan-site]').should(
        'have.length',
        3,
      );
      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(0)
        .should('contain.text', 'Primary Port');
      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(1)
        .should('contain.text', 'Mining Installation');
      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(2)
        .should('contain.text', 'Industrial Installation')
        .and('contain.text', 'OK');

      cy.visit('/plan');
      cy.get('h1').should('have.text', systemName);
      cy.get('[data-plan-build-order] [data-plan-site]').should(
        'have.length',
        3,
      );

      cy.window().then((window) => {
        cy.stub(window, 'confirm').returns(true).as('confirmRaven');
      });
      cy.contains('button', /^Import from Raven$/).click();
      cy.get(
        'input[aria-label="Import Raven Colonial layout file"]',
      ).selectFile('cypress/fixtures/plan/raven-layout.json', { force: true });
      cy.get('@confirmRaven').should('have.been.calledOnce');
      cy.get('[data-plan-build-order] [data-plan-site]').should(
        'have.length',
        2,
      );
      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(0)
        .should('contain.text', 'Lantern Harbour')
        .and('contain.text', 'Primary Port');
      cy.get('[data-plan-build-order] [data-plan-site]')
        .eq(1)
        .should('contain.text', 'Copper Quarry')
        .and('contain.text', 'A A Belt')
        .and('not.contain.text', 'Cluster 3');
      cy.contains('summary', /^Import notes \(/).click();
      cy.contains('li', /Cluster 3/).should('contain.text', 'A A Belt');
      cy.get('[aria-live="polite"]').should('contain.text', '0 blocked');
      cy.injectAxe();
      cy.checkA11y();
      cy.document().should((document) => {
        expect(document.documentElement.scrollWidth).to.be.at.most(width);
      });
      cy.screenshot(`plan/raven-${Cypress.browser.name}-${width}x${height}`, {
        capture: 'fullPage',
        overwrite: true,
      });
    });
  }
});
