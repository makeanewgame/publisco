import { API_BASE_URL } from './apiConfig';
import { store } from '../app/store';
import { clearCredentials } from '../app/authSlice';

const API_BASE = API_BASE_URL;

export class AuthExpiredError extends Error {}

function clearSession() {
  // clearCredentials() also clears the localStorage tokens/user — dispatching
  // it (rather than clearing storage directly) keeps Redux in sync so
  // RequireAuth notices and redirects instead of leaving a stale user in state.
  store.dispatch(clearCredentials());
}

// The backend rotates refresh tokens (the old one is revoked as soon as a new
// one is issued), so two concurrent 401s must not each call /auth/refresh with
// the same token independently — the second call would race against the
// first's rotation and lose, wiping out the session the first call just
// refreshed. All concurrent callers share this single in-flight promise instead.
let refreshPromise: Promise<string> | null = null;

function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = localStorage.getItem('refreshToken');
      if (!refreshToken) {
        throw new AuthExpiredError('No refresh token available.');
      }

      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refreshToken }),
      });

      if (!response.ok) {
        throw new AuthExpiredError('Refresh token rejected.');
      }

      const data: { accessToken: string; refreshToken: string } = await response.json();
      localStorage.setItem('accessToken', data.accessToken);
      localStorage.setItem('refreshToken', data.refreshToken);
      return data.accessToken;
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

// JWT_ACCESS_EXPIRES_IN is 15m on the backend, so any session left open
// longer than that needs a silent refresh before hitting protected routes.
// On 401, refresh once and retry; if the refresh itself fails, clear the
// stale session and surface AuthExpiredError so callers can send the user
// back to sign-in instead of looping on 401s.
export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const attempt = () => {
    const token = localStorage.getItem('accessToken');
    const headers = new Headers(init.headers);
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    return fetch(`${API_BASE}${path}`, { ...init, headers });
  };

  let response = await attempt();
  if (response.status === 401) {
    try {
      await refreshAccessToken();
    } catch (error) {
      clearSession();
      throw error instanceof AuthExpiredError ? error : new AuthExpiredError('Session expired.');
    }
    response = await attempt();
  }
  return response;
}
