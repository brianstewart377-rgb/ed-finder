# Task 26F-UX-7 rendered evidence

Captured from the real flagged local Map route at 1280x720 with
`VITE_STAGE26E_PRODUCTION_MAP=enabled`.

## Two-line region labels

[`wrapped-region-labels.png`](./wrapped-region-labels.png) shows the whole
galaxy at its default framing. Browser layout measurements confirmed:

- `Inner Orion-Perseus Conflux`: 26.00 px high at a 12.98 px line height
  (two lines).
- `Outer Scutum-Centaurus Arm`: 26.00 px high at a 12.98 px line height
  (two lines).
- `Sagittarius-Carina Arm`: 13.00 px high (one line).
- `Xibalba`: 13.00 px high (one line).

This demonstrates that the general 148 px balanced-wrap rule only wraps names
that need it.

## Persistent current-region indicator

The camera began in `Galactic Centre`, then keyboard pan moved its world-space
centre into `Odin's Hold`. After zooming to 13.29 LY/px and panning away from
the ordinary label anchor, normal decluttering left only `Ryker's Hope` and
`Izanami` in the ordinary label layer. The separate 10%-opacity ambient
indicator still showed `Odin's Hold`.

[`current-region-close-zoom.png`](./current-region-close-zoom.png) records
that close-zoom state. Exact camera and DOM observations are in
[`region-label-observation.json`](./region-label-observation.json).

The API was not running during this visual check; that does not affect the
static authoritative region asset or map camera interactions exercised here.
