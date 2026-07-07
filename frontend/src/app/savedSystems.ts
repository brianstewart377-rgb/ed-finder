import { ApiError } from '@/lib/api';

export type SavedSystemActionState = 'idle' | 'saving' | 'removing';

export interface SavedSystemNoticeState {
  tone: 'success' | 'error';
  message: string;
  detail: string;
  actionLabel?: string;
}

export function savedSystemFailureDetail(error: unknown, attemptedRemove: boolean): string {
  if (error instanceof ApiError) {
    if (attemptedRemove && error.status === 404) {
      return 'This system was already absent from saved systems, so the view has been refreshed.';
    }
    if (error.status === 404) {
      return 'This system is not available to save right now. Refresh and try again.';
    }
    if (error.status === 410) {
      return 'Saved systems need a current browser sync key. Refresh and try again.';
    }
    return 'Saved systems are unavailable right now. Please try again.';
  }
  return error instanceof Error ? error.message : 'The saved-system request did not complete.';
}
