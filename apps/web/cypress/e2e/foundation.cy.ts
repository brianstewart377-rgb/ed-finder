describe('ED-Finder V3 foundation', () => {
  for (const [width, height] of [
    [1280, 800],
    [1024, 768],
    [768, 1024],
    [390, 844],
  ] as const) {
    it(`keeps home and guest account usable at ${width}x${height}`, () => {
      cy.viewport(width, height);
      cy.intercept('GET', '/api/v1/auth/session').as('accountSession');
      cy.visit('/');
      cy.wait('@accountSession').its('response.statusCode').should('eq', 200);
      cy.contains('button', 'Sign in with Frontier').should('be.visible');
      cy.get('.workspace-header nav a').should(($links) => {
        expect(
          $links.toArray().map((link) => ({
            href: link.getAttribute('href'),
            label: link.textContent?.trim(),
          })),
        ).to.deep.equal([
          { href: '/explore', label: 'Explore' },
          { href: '/inspect', label: 'Inspect' },
          { href: '/plan', label: 'Plan' },
        ]);
      });
      cy.get('.tool-grid .tool-card').should('have.length', 3);
      cy.contains('.tool-card', 'Plan').should('have.attr', 'href', '/plan');
      cy.get('.upcoming-tools p')
        .should('have.length', 1)
        .and('contain.text', 'Review & export');
      cy.get('.upcoming-tools p > a')
        .should('have.text', 'Available in Plan')
        .and('have.attr', 'href', '/plan');
      cy.get('.galaxy-motif')
        .should('have.attr', 'aria-hidden', 'true')
        .find('a, button, [tabindex="0"]')
        .should('not.exist');
      cy.get('.hero-actions a').should(($actions) => {
        expect(
          $actions.toArray().map((action) => action.getAttribute('href')),
        ).to.deep.equal(['/explore', '/inspect']);
        const [primary, secondary] = $actions
          .toArray()
          .map((action) => action.getBoundingClientRect());
        $actions.toArray().forEach((action) => {
          const bounds = action.getBoundingClientRect();
          expect(action.scrollWidth).to.be.at.most(action.clientWidth);
          expect(bounds.left).to.be.at.least(0);
          expect(bounds.right).to.be.at.most(width);
        });
        expect(
          secondary.left >= primary.right || secondary.top >= primary.bottom,
          'Hero actions do not overlap',
        ).to.equal(true);
        if (width === 390) {
          expect(secondary.top).to.be.at.least(primary.bottom);
        }
      });
      cy.get('.tool-card').should(($cards) => {
        const cards = $cards.toArray();
        const bounds = cards.map((card) => card.getBoundingClientRect());
        cards.forEach((card, index) => {
          expect(card.scrollWidth).to.be.at.most(card.clientWidth);
          expect(bounds[index].left).to.be.at.least(0);
          expect(bounds[index].right).to.be.at.most(width);
          if (index === 0) return;
          if (width > 900) {
            expect(bounds[index].top).to.equal(bounds[0].top);
            expect(bounds[index].height).to.equal(bounds[0].height);
            expect(bounds[index].left).to.be.at.least(bounds[index - 1].right);
          } else {
            expect(bounds[index].left).to.equal(bounds[0].left);
            expect(bounds[index].width).to.equal(bounds[0].width);
            expect(bounds[index].top).to.be.at.least(bounds[index - 1].bottom);
          }
        });
      });
      cy.get('.tool-card p').should(($descriptions) => {
        $descriptions.toArray().forEach((description) => {
          const lineHeight = Number.parseFloat(
            getComputedStyle(description).lineHeight,
          );
          expect(
            description.getBoundingClientRect().height,
            `Single-line description: ${description.textContent}`,
          ).to.be.at.most(lineHeight + 1);
        });
      });
      cy.contains('.hero-actions a', 'Explore the galaxy').focus();
      cy.press(Cypress.Keyboard.Keys.TAB);
      cy.contains('.hero-actions a', 'Inspect a system').should('be.focused');
      for (const tool of ['Explore', 'Inspect', 'Plan']) {
        cy.press(Cypress.Keyboard.Keys.TAB);
        cy.contains('.tool-card', tool).should('be.focused');
      }
      cy.injectAxe();
      cy.checkA11y();
      cy.document().should((document) => {
        expect(document.documentElement.scrollWidth).to.be.at.most(width);
      });
      cy.screenshot(`account/home-${Cypress.browser.name}-${width}x${height}`, {
        capture: 'fullPage',
        overwrite: true,
      });

      cy.contains('.tool-card', 'Plan').click();
      cy.location('pathname').should('eq', '/plan');
      cy.contains('h1', 'Colony planner').should('be.visible');
      cy.get('.workspace-header nav a[aria-current="page"]')
        .should('have.length', 1)
        .and('have.attr', 'href', '/plan')
        .and('have.text', 'Plan');

      cy.visit('/account');
      cy.wait('@accountSession').its('response.statusCode').should('eq', 200);
      cy.contains('h2', 'Sign in to manage your account').should('be.visible');
      cy.contains('button', 'Sign in with Frontier')
        .focus()
        .should('be.focused');
      cy.injectAxe();
      cy.checkA11y();
      cy.document().should((document) => {
        expect(document.documentElement.scrollWidth).to.be.at.most(width);
      });
      cy.screenshot(
        `account/guest-${Cypress.browser.name}-${width}x${height}`,
        {
          capture: 'fullPage',
          overwrite: true,
        },
      );
      cy.reload();
      cy.wait('@accountSession').its('response.statusCode').should('eq', 200);
      cy.contains('h2', 'Sign in to manage your account').should('be.visible');
      cy.get('.workspace-header nav a')
        .contains('Explore')
        .focus()
        .should('be.focused');
      cy.press(Cypress.Keyboard.Keys.ENTER);
      cy.location('pathname').should('eq', '/explore');
      cy.get('h1').should('contain.text', 'Chart a promising system');
    });
  }

  it('loads the shell and exercises the real same-origin bootstrap', () => {
    cy.intercept('/api/health').as('health');
    cy.intercept('/api/v1/auth/session').as('session');
    cy.visit('/');
    cy.get('h1').should('contain.text', 'Search the galaxy').and('be.visible');
    cy.wait('@health').its('response.statusCode').should('eq', 200);
    cy.wait('@session').its('response.statusCode').should('eq', 200);
    cy.contains('dd', 'Connected').should('be.visible');
    cy.contains('dd', 'Guest').should('be.visible');
    cy.contains('button', 'Sign in with Frontier').should('be.visible');
  });

  it('proxies backend-owned routes to the disposable FastAPI service', () => {
    cy.request('/openapi.json?format=json').then(
      ({ body, headers, status }) => {
        expect(status).to.eq(200);
        expect(headers['content-type']).to.include('application/json');
        expect(body.paths).to.have.property('/api/health');
      },
    );

    cy.request({
      url: '/s/0?utm=x',
      followRedirect: false,
      failOnStatusCode: false,
    }).then(({ headers, status }) => {
      // FastAPI currently owns this valid numeric share route and redirects
      // browser user agents to canonical Inspect. A Svelte fallback would
      // instead return HTML 200.
      expect(status).to.eq(302);
      expect(headers.location).to.include('/inspect?system=0');
    });

    cy.request({ url: '/apiary', failOnStatusCode: false }).then(
      ({ headers, status }) => {
        // This near-prefix must remain on the Svelte side. Because it is not a
        // real application route, the correct frontend response is its HTML 404.
        expect(status).to.eq(404);
        expect(headers['content-type']).to.include('text/html');
      },
    );
  });

  it('supports direct navigation and refresh through the SPA fallback', () => {
    cy.visit('/explore');
    cy.get('h1')
      .should('contain.text', 'Chart a promising system')
      .and('be.visible');
    cy.get('[role="status"][data-renderer-state="ready"]', {
      timeout: 20_000,
    }).should('be.visible');
    cy.reload();
    cy.get('h1')
      .should('contain.text', 'Chart a promising system')
      .and('be.visible');
  });

  it('rejects unknown journey routes instead of rendering a placeholder', () => {
    cy.visit('/explroe', { failOnStatusCode: false });
    cy.contains('Chart a promising system').should('not.exist');
    cy.contains(/not found/i).should('be.visible');
  });
});

describe('Home reduced motion', { browser: { family: 'chromium' } }, () => {
  afterEach(() => {
    cy.then(() =>
      Cypress.automation('remote:debugger:protocol', {
        command: 'Emulation.setEmulatedMedia',
        params: { features: [] },
      }),
    );
  });

  it('keeps home actions and cards still when keyboard focused', () => {
    cy.then(() =>
      Cypress.automation('remote:debugger:protocol', {
        command: 'Emulation.setEmulatedMedia',
        params: {
          features: [{ name: 'prefers-reduced-motion', value: 'reduce' }],
        },
      }),
    );
    cy.visit('/');
    cy.window().should((window) => {
      expect(
        window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      ).to.equal(true);
    });
    cy.get('.hero-actions a, .tool-card').each(($action) => {
      cy.wrap($action)
        .focus()
        .should('be.focused')
        .should(($focused) => {
          const style = getComputedStyle($focused[0]);
          expect(style.animationName).to.equal('none');
          expect(style.transitionDuration).to.equal('0s');
        });
    });
    cy.injectAxe();
    cy.checkA11y();
  });
});
