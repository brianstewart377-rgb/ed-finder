describe('ED-Finder V3 foundation', () => {
  it('loads the shell and exercises the real same-origin bootstrap', () => {
    cy.intercept('/api/auth/session').as('session');
    cy.visit('/');
    cy.get('h1').should('contain.text', 'Finder').and('be.visible');
    cy.wait('@session').its('response.statusCode').should('eq', 200);
    cy.get('[data-testid="frontier-sign-in"]').should('be.visible');
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
      // browser user agents. A Svelte fallback would instead return HTML 200.
      expect(status).to.eq(302);
      expect(headers.location).to.include('/#system/0');
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
    cy.get('h1').should('have.text', 'Explore').and('be.visible');
    cy.reload();
    cy.contains('This product surface has not been ported yet.').should(
      'be.visible',
    );
  });

  it('rejects unknown journey routes instead of rendering a placeholder', () => {
    cy.visit('/explroe', { failOnStatusCode: false });
    cy.contains('This product surface has not been ported yet.').should(
      'not.exist',
    );
    cy.contains(/not found/i).should('be.visible');
  });

  it('replaces warm legacy hashes and retains lossless oversized ids', () => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    cy.visit('/?source=legacy#map/system/18446744073709551615');
    cy.location('pathname').should('eq', '/explore');
    cy.location('search')
      .should('include', 'source=legacy')
      .and('include', 'system=18446744073709551615');
    cy.location('hash').should('eq', '');
    cy.get('[data-testid="system-detail-modal"]')
      .should('contain.text', '18446744073709551615')
      .and('be.focused');
  });

  it('replaces a hash assigned after boot without looping', () => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    cy.visit('/compare');
    cy.window().then((browser) => {
      browser.location.hash = '#system/9007199254740993';
    });
    cy.location('pathname').should('eq', '/compare');
    cy.location('search').should('eq', '?system=9007199254740993');
    cy.location('hash').should('eq', '');
  });

  it('hydrates the canonical selected-system storage boundary losslessly', () => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    cy.visit('/', {
      onBeforeLoad(browser) {
        browser.localStorage.setItem(
          'ed-finder:selected-system-context',
          '18446744073709551615',
        );
      },
    });
    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      '18446744073709551615',
    );
  });

  it('restores the host URL and scroll contract when Escape closes detail', () => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    cy.visit('/compare');
    cy.get('a[href="/compare"]')
      .focus()
      .then(($link) => {
        cy.window().then((browser) => {
          browser.history.replaceState(
            {},
            '',
            '/compare?system=9007199254740993',
          );
          browser.dispatchEvent(new PopStateEvent('popstate'));
        });
        cy.get('[data-testid="system-detail-modal"]').should('be.visible');
        cy.get('body').should('have.css', 'overflow', 'hidden');
        cy.get('body').type('{esc}');
        cy.wrap($link).should('be.focused');
      });
    cy.get('[data-testid="system-detail-modal"]').should('not.exist');
    cy.location('pathname').should('eq', '/compare');
    cy.location('search').should('eq', '');
    cy.get('body').should('not.have.css', 'overflow', 'hidden');
  });

  it('gates signed-out, non-owner, and owner admin states', () => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    }).as('guest');
    cy.visit('/admin');
    cy.get('[data-testid="owner-sign-in-required"]').should('be.visible');
    cy.intercept('/api/auth/session', {
      authenticated: true,
      user: { commander_name: 'Player', is_owner: false },
      owner_claim_available: false,
    }).as('player');
    cy.reload();
    cy.get('[data-testid="owner-access-denied"]').should('be.visible');
    cy.intercept('/api/auth/session', {
      authenticated: true,
      user: { commander_name: 'Owner', is_owner: true },
      owner_claim_available: false,
    }).as('owner');
    cy.reload();
    cy.get('[data-testid="admin-tab"]').should('be.visible');
  });
});
