Cypress.Commands.add('getByTestId', (testId, options = {}) => (
  cy.get(`[data-testid="${testId}"]`, options)
));

Cypress.Commands.add('assertCanvasSynced', () => {
  cy.get('.map-foundation-renderer canvas').should(($canvas) => {
    const canvas = $canvas[0];
    const rect = canvas.getBoundingClientRect();
    expect(rect.width, 'canvas css width').to.be.greaterThan(0);
    expect(rect.height, 'canvas css height').to.be.greaterThan(0);
    expect(canvas.width, 'drawing buffer width').to.equal(Number(canvas.dataset.drawingBufferWidth));
    expect(canvas.height, 'drawing buffer height').to.equal(Number(canvas.dataset.drawingBufferHeight));
    expect(Number(canvas.dataset.viewportX), 'viewport x').to.equal(0);
    expect(Number(canvas.dataset.viewportY), 'viewport y').to.equal(0);
    expect(Number(canvas.dataset.viewportWidth), 'viewport width').to.equal(Number(canvas.dataset.drawingBufferWidth));
    expect(Number(canvas.dataset.viewportHeight), 'viewport height').to.equal(Number(canvas.dataset.drawingBufferHeight));
    expect(canvas.dataset.drawingBufferSynced, 'sync guard').to.equal('true');
    expect(canvas.dataset.contextLost, 'WebGL context').not.to.equal('true');
  });
});

before(() => {
  cy.request({
    url: '/api/health',
    retryOnNetworkFailure: true,
    retryOnStatusCodeFailure: true,
  }).its('status').should('eq', 200);
});
