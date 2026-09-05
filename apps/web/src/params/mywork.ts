import type { ParamMatcher } from '@sveltejs/kit';
export const match: ParamMatcher = (value) =>
  ['watchlist', 'pinned', 'colony'].includes(value);
