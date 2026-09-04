import { claimOwner, getAuthSession, logout } from '$lib/api/client';
import type { AuthSessionResponse } from '$lib/api/generated';
const empty: AuthSessionResponse = {
  authenticated: false,
  user: null,
  owner_claim_available: false,
};
export class AuthState {
  session = $state<AuthSessionResponse>(empty);
  loading = $state(true);
  error = $state('');
  async refresh() {
    this.loading = true;
    this.error = '';
    try {
      this.session = await getAuthSession();
    } catch (e) {
      this.session = empty;
      this.error = e instanceof Error ? e.message : String(e);
    } finally {
      this.loading = false;
    }
  }
  signIn() {
    const returnTo = location.pathname + location.search;
    location.assign(
      `/api/auth/frontier/login?return_to=${encodeURIComponent(returnTo)}`,
    );
  }
  async signOut() {
    this.session = await logout();
    if (['/admin', '/operator'].includes(location.pathname))
      location.assign('/finder');
  }
  async claim(token: string) {
    this.session = await claimOwner(token);
  }
}
export const authState = new AuthState();
