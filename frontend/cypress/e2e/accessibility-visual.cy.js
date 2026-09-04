describe('accessibility and visual evidence capabilities', () => {
  beforeEach(() => {
    cy.viewport(1280, 720);
    cy.visit('/');
    cy.get('#root').should('be.visible');
  });

  it('runs axe against WCAG 2 A and AA rules', () => {
    cy.injectAxe();
    cy.checkA11y(null, {
      runOnly: {
        type: 'tag',
        values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'],
      },
    });
  });

  it('captures a fixed-viewport deterministic visual baseline', () => {
    cy.get('#root').should(($root) => {
      expect($root[0].scrollWidth, 'root width').to.be.at.most(1280);
    });
    cy.captureDeterministicBaseline('application-shell-1280x720', {
      blackout: ['canvas'],
    });
  });
});
