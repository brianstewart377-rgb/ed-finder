# V2 visual identity and account controls: first pass

This is a design-review draft for the current Svelte application. It has not
been deployed. The Ratings and Search workers were not changed.

`ed-finder-ui-preview.html` is a standalone static export of the actual home
page and shared-header components, with the built application CSS inlined.
The component render used a guest session and connected-health test fixture.
The file labels those fixtures and disconnects navigation; it is not a live
health receipt, interactive authentication demo, screenshot, or approved visual
baseline. Open it locally to review the responsive design.

The visual reference is `frontend/src/index.css`: ED orange `#ff7a14`, charcoal,
gunmetal, silver text and restrained warm highlights. No V2 runtime, copied
media, new external fonts or production settings are introduced. The central
compass/rings are decorative, not a representation of catalogue data.

The cloud browser inspected the live homepage and confirmed it had no sign-in
control. Navigating the existing `/api/v1/auth/frontier/login` route reached
Frontier's authentication form. No credentials were entered; successful callback,
account creation and subsequent logout have not been proved in production.

Validation completed locally: Node 24, pinned pnpm 11.25.0, Svelte check with no
errors or warnings, lint, formatting, production build, all 167 Svelte tests,
28 focused Python web-contract tests, and asset provenance. The four new account
component tests cover guest sign-in, loading/error/retry, account navigation,
duplicate logout prevention and a failed logout.

The cloud browser's URL security policy blocked local preview access. Desktop,
mobile, keyboard and real-browser visual acceptance remain outstanding. Do not
promote this draft until those checks and the normal exact-head PR acceptance
gates are complete. No screenshot or visual pass is claimed here.

The next account/journal/importer work is scoped in
`docs/development/accounts-journal-ui-plan.md`.
