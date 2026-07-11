const OPERATOR_SELECTED_SOURCE_RUN_KEY = 'ed_operator_selected_source_run';

export function readSelectedOperatorSourceRun(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const value = window.sessionStorage.getItem(OPERATOR_SELECTED_SOURCE_RUN_KEY)?.trim() ?? '';
    return value || null;
  } catch {
    return null;
  }
}

export function writeSelectedOperatorSourceRun(sourceRunKey: string | null) {
  if (typeof window === 'undefined') return;
  try {
    if (!sourceRunKey?.trim()) {
      window.sessionStorage.removeItem(OPERATOR_SELECTED_SOURCE_RUN_KEY);
      return;
    }
    window.sessionStorage.setItem(OPERATOR_SELECTED_SOURCE_RUN_KEY, sourceRunKey.trim());
  } catch {
    // Best-effort UI handoff only.
  }
}
