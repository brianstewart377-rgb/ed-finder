export const STAGE26E_PRODUCTION_MAP_FLAG = 'VITE_STAGE26E_PRODUCTION_MAP' as const;

/**
 * Stage 26E route composition is deliberately opt-in. Only the exact value
 * `enabled` activates the candidate; unset, malformed, and truthy-looking
 * values all keep the established map renderer live.
 */
export function isStage26EProductionMapEnabled(
  value: string | boolean | undefined = import.meta.env.VITE_STAGE26E_PRODUCTION_MAP,
): boolean {
  return value === 'enabled';
}
