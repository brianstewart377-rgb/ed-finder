// Representative RGB for a stellar spectral class (a small blackbody
// approximation keyed on the first letter of the class). Shared by the
// system-detail body thumbnails and the map's real-star layer. The
// full-fidelity Mitchell-Charity table is deferred to map feature #1.

const STAR_COLORS: Record<string, string> = {
  O: '#9bb0ff', B: '#aabfff', A: '#e6ecff', F: '#fbf8ff',
  G: '#fff4e8', K: '#ffd6a0', M: '#ffb37a', L: '#ff8a5c',
  T: '#d1663f', Y: '#a04a3a', W: '#a6c0ff', // Wolf-Rayet -> blue
  N: '#ffcf9c', S: '#ffb37a', C: '#ff7a5c', // carbon stars -> reddish
  D: '#dfe8ff',                              // white dwarf
};

const DEFAULT_STAR_COLOR = '#ffe0b0';

export function spectralStarColor(spectralClass?: string | null): string {
  const first = (spectralClass ?? '').trim().charAt(0).toUpperCase();
  return STAR_COLORS[first] ?? DEFAULT_STAR_COLOR;
}
