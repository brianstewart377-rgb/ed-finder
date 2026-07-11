import { readSessionStorageItem, removeSessionStorageItem, writeSessionStorageItem } from '@/lib/browserStorage';

const OPERATOR_SELECTED_SOURCE_RUN_KEY = 'ed_operator_selected_source_run';

export function readSelectedOperatorSourceRun(): string | null {
  const value = readSessionStorageItem(OPERATOR_SELECTED_SOURCE_RUN_KEY)?.trim() ?? '';
  return value || null;
}

export function writeSelectedOperatorSourceRun(sourceRunKey: string | null) {
  if (!sourceRunKey?.trim()) {
    removeSessionStorageItem(OPERATOR_SELECTED_SOURCE_RUN_KEY);
    return;
  }
  writeSessionStorageItem(OPERATOR_SELECTED_SOURCE_RUN_KEY, sourceRunKey.trim());
}
