import { error } from '@sveltejs/kit';
import { parseId64 } from '$lib/domain/id64';
export function load({ params }) {
  try {
    return { id64: parseId64(params.id64) };
  } catch {
    error(404, 'Invalid system identifier');
  }
}
