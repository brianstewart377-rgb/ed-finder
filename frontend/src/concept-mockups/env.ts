import { createContext, useContext } from 'react';

// Shared environment (viewport + motion preference) for the concept gallery.
// Kept separate from component exports so React Fast Refresh stays happy.
export type Viewport = 'desktop' | 'laptop' | 'mobile';

export interface GalleryEnv {
  viewport: Viewport;
  reducedMotion: boolean;
}

export type StatusTone = 'ok' | 'info' | 'warn' | 'idle' | 'active';

export const GalleryEnvContext = createContext<GalleryEnv>({ viewport: 'desktop', reducedMotion: false });

export const useGalleryEnv = (): GalleryEnv => useContext(GalleryEnvContext);

/** Returns transition utility classes, or '' when reduced motion is requested. */
export function motion(reducedMotion: boolean, classes: string): string {
  return reducedMotion ? '' : classes;
}
