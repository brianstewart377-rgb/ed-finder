# Task 26F-DEPLOY-11 cross-browser evidence

The production bundle was built with `yarn build` and served with
`yarn preview --port 4173 --strictPort`.

`live-baseline-sw-response.json` records the pre-fix public response:
`https://ed-finder.app/sw.js` returned HTTP 200 but `text/html`, beginning
with `<!doctype html>`. That is the SPA fallback, not a worker script.

Playwright exercised Chromium, Firefox, and the installed Microsoft Edge
channel. Each browser:

1. loaded a fresh browser context;
2. installed `/sw.js` and waited for its active worker to control the page;
3. opened the whole-galaxy map;
4. resized from 1280 x 720 to 1111 x 733 and back;
5. checked CSS canvas size, canvas attributes, WebGL drawing-buffer size,
   GL viewport, and context state; and
6. captured a rendered screenshot.

`cross-browser-runtime.json` records the exact browser versions and runtime
measurements. All three workers were `activated`, `/sw.js` returned
`text/javascript`, and no service-worker registration errors were observed.
All three drawing buffers and GL viewports matched the 1280 x 720 displayed
canvas after the resize cycle, with no destination-rectangle/viewport warning.

The Firefox and Edge screenshots visibly show the generated 18,000-point
starfield behind the region boundaries. Headless Firefox did not reproduce
the owner's hardware-specific warning before the fix, so the evidence proves
the new synchronization guarantee in the available Firefox runtime rather
than claiming reproduction of that exact GPU/driver combination.
