import type { Route } from '@/hooks/useHashRoute';
import type { PrimaryWorkspace, WorkspaceMeta } from './types';

export function primaryWorkspaceForRoute(route: Route): PrimaryWorkspace | null {
  if (route === 'finder' || route === 'map' || route === 'search-tuning') return 'explore';
  if (route === 'my-work' || route === 'watchlist' || route === 'pinned' || route === 'colony-planner') return 'plan';
  if (route === 'compare' || route === 'fc') return 'review';
  return null;
}

export function isRouteActive(current: Route, target: Route): boolean {
  if (current === target) return true;
  if (target === 'my-work' && (current === 'watchlist' || current === 'pinned')) return true;
  return false;
}

export function workspaceMetaForRoute(route: Route): WorkspaceMeta {
  switch (route) {
    case 'finder':
      return {
        title: 'Finder',
        primaryLabel: 'Explore',
        supportingText: 'Find promising systems. Save them for later or inspect them before starting a plan.',
        nextAction: 'Save systems for later or inspect them before starting a plan.',
        statusLabel: 'Finder',
        statusTone: 'available',
      };
    case 'map':
      return {
        title: 'Galactic Map',
        primaryLabel: 'Explore',
        supportingText: 'Use the map as a secondary Explore aid for current Finder results. It stays discoverability-focused and does not become a planning cockpit in this slice.',
        nextAction: 'Inspect a mapped system or return to Finder for the main discovery flow.',
        statusLabel: 'Secondary Explore surface',
        statusTone: 'available',
      };
    case 'search-tuning':
      return {
        title: 'Development Tuning',
        primaryLabel: 'Explore',
        supportingText: 'Refine discovery weighting and candidate filters without changing the core Finder or planning logic.',
        nextAction: 'Run a search, inspect a candidate, then enter Plan from a real system.',
        statusLabel: 'Explore support tool',
        statusTone: 'available',
      };
    case 'colony-planner':
      return {
        title: 'Colony Planner',
        primaryLabel: 'Plan',
        supportingText: 'Use the canonical live planning workspace for serious colony planning. Simulation preview remains reusable inventory only and is not wired here.',
        nextAction: 'Plan from a selected system or return to Explore to choose one safely.',
        statusLabel: 'Canonical live planner',
        statusTone: 'canonical',
      };
    case 'my-work':
      return {
        title: 'My Work',
        primaryLabel: 'Plan',
        supportingText: 'Return to saved systems, local plans, and established colony work without splitting that context between Watchlist, Pins, and the planner.',
        nextAction: 'Resume a saved system, continue a plan, or review established colony work.',
        statusLabel: 'Player planning home',
        statusTone: 'available',
      };
    case 'watchlist':
      return {
        title: 'My Work',
        primaryLabel: 'Plan',
        supportingText: 'Watchlist now feeds the Saved Systems view in My Work so synced saved candidates sit beside local planning context.',
        nextAction: 'Inspect a saved system or start planning from a deliberate hand-off.',
        statusLabel: 'Player planning home',
        statusTone: 'available',
      };
    case 'pinned':
      return {
        title: 'My Work',
        primaryLabel: 'Plan',
        supportingText: 'Pins now feed the Saved Systems view in My Work so local shortlist context stays beside saved systems and plans.',
        nextAction: 'Inspect a saved system or continue from active planning work.',
        statusLabel: 'Player planning home',
        statusTone: 'available',
      };
    case 'compare':
      return {
        title: 'Compare',
        primaryLabel: 'Review',
        supportingText: 'Review candidate systems side by side before committing to a plan. This remains a decision-support surface, not a planning workspace.',
        nextAction: 'Inspect a compared system or return to Explore to find a better candidate.',
        statusLabel: 'Decision review',
        statusTone: 'available',
      };
    case 'fc':
      return {
        title: 'FC Route Planner',
        primaryLabel: 'Review',
        supportingText: 'Use fleet-carrier routing as a supporting tool for player logistics without turning it into a primary Explore or Plan workspace.',
        nextAction: 'Review route support needs, then return to Explore or Plan for system work.',
        statusLabel: 'Supporting tool',
        statusTone: 'available',
      };
    case 'admin':
      return {
        title: 'Admin',
        primaryLabel: 'Operator',
        supportingText: 'Admin tools remain separate from normal player navigation and are not promoted into the Explore, Plan, or Review hierarchy.',
        nextAction: 'Use only when operator/admin access is intentionally required.',
        statusLabel: 'Operator-only tools',
        statusTone: 'caution',
      };
    case 'operator':
      return {
        title: 'Operator Cockpit',
        primaryLabel: 'Operator',
        supportingText: 'Read-only operator surfaces remain outside the normal player shell and are not part of the player-facing primary hierarchy.',
        nextAction: 'Use only for guarded operator review tasks.',
        statusLabel: 'Operator-only tools',
        statusTone: 'caution',
      };
  }
}
