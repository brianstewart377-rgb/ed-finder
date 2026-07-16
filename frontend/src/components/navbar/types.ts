import type { Route } from '@/hooks/useHashRoute';

export type PrimaryWorkspace = 'explore' | 'plan' | 'review';

export interface RouteDescriptor {
  route: Route;
  label: string;
  testid: string;
  badge?: number;
  title?: string;
}

export interface WorkspaceMeta {
  title: string;
  primaryLabel: string;
  supportingText: string;
  nextAction: string;
  statusLabel: string;
  statusTone: 'available' | 'canonical' | 'caution';
}
