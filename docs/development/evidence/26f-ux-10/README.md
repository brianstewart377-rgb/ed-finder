# Task 26F-UX-10 rendered evidence

The preview was started from `frontend/` with
`VITE_STAGE26E_PRODUCTION_MAP=enabled`.

## Fresh-load keyboard check

`fresh-load-keyboard-observation.json` records three full navigations to
fresh, uniquely queried Map URLs. After each load:

- `document.activeElement` was `BODY`, not the map renderer.
- No click or locator focus was performed.
- A tab-level `W` keypress moved the camera centre and produced a completed
  eased-pan telemetry trace.

This validates the exact failure case in the browser available to Codex:
keyboard input works after a fresh navigation without a trusted pointer
gesture or programmatic renderer focus. It cannot by itself certify every
browser/OS combination, but the implementation no longer depends on browsers
honouring a post-mount `.focus()` call.

## Control hint

`fresh-load-visible-controls.png` is a real rendered 1280 x 720 preview. The
control card begins at y=240, below the global navigation (bottom y=93.33),
and the persistent control row renders at 11px / weight 600 in the brighter
ED-Finder orange-on-dark treatment.

The prior production rule placed the same card at y=14.4, underneath the
global navigation, which explained why its text existed in the DOM but was
not visible to the owner.
