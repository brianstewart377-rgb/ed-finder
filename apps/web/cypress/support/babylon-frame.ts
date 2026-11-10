export function captureSubmittedBabylonFrame(name: string): void {
  let screenshotPath = '';
  cy.get<HTMLCanvasElement>('.spatial-canvas canvas')
    .should('be.visible')
    .screenshot(name, {
      overwrite: true,
      // Keep demand-render scheduling live while Cypress scrolls/captures.
      disableTimersAndAnimations: false,
      onAfterScreenshot(_element, props) {
        screenshotPath = props.path;
      },
    });
  // Inspect the compositor capture, not drawImage(WebGPUCanvas): the latter
  // can return empty pixels after presentation even while the displayed frame is
  // correct. The canvas-only image excludes headings, controls and status text.
  cy.then(() => cy.readFile<string>(screenshotPath, 'base64')).then(
    async (base64) => {
      const capturedFrame = new Image();
      await new Promise<void>((resolve, reject) => {
        capturedFrame.onload = () => resolve();
        capturedFrame.onerror = () => reject(new Error('Invalid canvas PNG'));
        capturedFrame.src = `data:image/png;base64,${base64}`;
      });
      const probe = document.createElement('canvas');
      probe.width = 128;
      probe.height = 64;
      const context = probe.getContext('2d');
      expect(context, '2-D visual probe').not.to.equal(null);
      context!.drawImage(capturedFrame, 0, 0, probe.width, probe.height);
      const pixels = context!.getImageData(
        0,
        0,
        probe.width,
        probe.height,
      ).data;
      let visibleSignalPixels = 0;
      for (let index = 0; index < pixels.length; index += 4) {
        if (pixels[index]! + pixels[index + 1]! + pixels[index + 2]! > 40) {
          visibleSignalPixels += 1;
        }
      }
      expect(
        visibleSignalPixels,
        'non-background pixels in the captured Babylon frame',
      ).to.be.greaterThan(10);
    },
  );
}
