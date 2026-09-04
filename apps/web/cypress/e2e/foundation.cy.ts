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

    cy.request('/apiary').then(({ body, headers, status }) => {
      // This near-prefix remains on the Svelte side and receives the same
      // transport-level SPA fallback as every other frontend-owned route.
      expect(status).to.eq(200);
      expect(headers['content-type']).to.include('text/html');
      expect(body).to.include('<!doctype html>');
    });
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
    cy.visit('/explroe');
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
    // Wait for AppShell.onMount to install the hashchange listener before
    // simulating a hash assigned by an already-running legacy integration.
    cy.get('[data-testid="frontier-sign-in"]').should('be.visible');
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

  it('lets a cold URL overlay replace an older durable selection', () => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    cy.visit('/explore?system=18446744073709551615', {
      onBeforeLoad(browser) {
        browser.localStorage.setItem(
          'ed-finder:selected-system-context',
          '9007199254740993',
        );
      },
    });
    cy.get('[data-testid="system-detail-modal"]')
      .should('contain.text', '18446744073709551615')
      .and('be.visible');
    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      '18446744073709551615',
    );
    cy.window().then((browser) => {
      expect(
        browser.localStorage.getItem('ed-finder:selected-system-context'),
      ).to.eq('18446744073709551615');
    });
  });

  it('establishes a cold direct system route without opening an overlay', () => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    cy.visit('/system/18446744073709551615', {
      onBeforeLoad(browser) {
        browser.localStorage.setItem(
          'ed-finder:selected-system-context',
          '9007199254740993',
        );
      },
    });
    cy.get('h1').should('have.text', 'System Detail');
    cy.get('[data-testid="system-detail-modal"]').should('not.exist');
    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      '18446744073709551615',
    );
    cy.window().then((browser) => {
      expect(
        browser.localStorage.getItem('ed-finder:selected-system-context'),
      ).to.eq('18446744073709551615');
    });

    cy.reload();
    cy.location('pathname').should('eq', '/system/18446744073709551615');
    cy.get('h1').should('have.text', 'System Detail');
    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      '18446744073709551615',
    );
  });

  it('rejects malformed and traversal-like cold paths without exposing files', () => {
    const unsafePaths = [
      '/bad%E0%A4%A',
      '/bad%00path',
      '/%5c..%5cpackage.json',
      '/safe%2f..%2f..%2fpackage.json',
    ];

    for (const url of unsafePaths) {
      cy.request({ url, failOnStatusCode: false }).then(({ body, status }) => {
        expect(status, url).to.eq(400);
        expect(String(body), url).to.eq('Bad request path\n');
        expect(String(body), url).not.to.include('@ed-finder/web');
        expect(String(body), url).not.to.include('ED-Finder Agent Contract');
      });
    }
  });

  it('hydrates the selected-system singleton exactly once on bootstrap', () => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    let selectedSystemReads = 0;
    cy.visit('/my-work', {
      onBeforeLoad(browser) {
        browser.localStorage.setItem(
          'ed-finder:selected-system-context',
          '9007199254740993',
        );
        const storagePrototype = Object.getPrototypeOf(
          browser.localStorage,
        ) as Storage;
        const getItem = storagePrototype.getItem;
        storagePrototype.getItem = function (key: string) {
          if (key === 'ed-finder:selected-system-context')
            selectedSystemReads += 1;
          return getItem.call(this, key);
        };
      },
    });
    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      '9007199254740993',
    );
    cy.then(() => expect(selectedSystemReads).to.eq(1));
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
    cy.get('[data-testid="selected-system-context"]').should(
      'contain.text',
      '9007199254740993',
    );
    cy.window().then((browser) => {
      expect(
        browser.localStorage.getItem('ed-finder:selected-system-context'),
      ).to.eq('9007199254740993');
    });
    cy.location('pathname').should('eq', '/compare');
    cy.location('search').should('eq', '');
    cy.get('body').should('not.have.css', 'overflow', 'hidden');
  });

  it('updates durable selected-system context across tabs at uint64 max', () => {
    cy.intercept('/api/auth/session', {
      authenticated: false,
      user: null,
      owner_claim_available: false,
    });
    cy.visit('/my-work');
    cy.window().then((browser) => {
      browser.localStorage.setItem(
        'ed-finder:selected-system-context',
        '18446744073709551615',
      );
      browser.dispatchEvent(
        new StorageEvent('storage', {
          key: 'ed-finder:selected-system-context',
          newValue: '18446744073709551615',
          storageArea: browser.localStorage,
        }),
      );
    });
    cy.get('[data-testid="selected-system-context"]')
      .should('contain.text', '18446744073709551615')
      .find('a')
      .should(
        'have.attr',
        'href',
        '/colony-planner/system/18446744073709551615',
      );
    cy.get('[data-testid="system-detail-modal"]').should('not.exist');
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
