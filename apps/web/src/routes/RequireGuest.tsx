import { useEffect, useState } from 'react';
import { useSelector } from 'react-redux';
import { Navigate, Outlet } from 'react-router-dom';
import { selectCurrentUser } from '../app/authSlice';
import { authFetch } from '../lib/authFetch';

// `user` in localStorage/Redux only reflects the last successful sign-in — it
// isn't cleared just because the access/refresh tokens later expired (that
// only happens once something calls a protected endpoint via `authFetch`).
// A stale `user` here would make this guard bounce a session-expired visitor
// straight back to "/" the moment they click "sign in"/"sign up" in the
// footer, with no way back in. So a truthy `user` is re-verified against
// `/auth/me` (which itself refreshes/clears the session on 401) before we
// treat them as still logged in.
export function RequireGuest() {
  const user = useSelector(selectCurrentUser);
  const [verified, setVerified] = useState<'checking' | 'valid' | 'invalid'>(
    user ? 'checking' : 'invalid',
  );

  useEffect(() => {
    if (!user) {
      setVerified('invalid');
      return;
    }
    let cancelled = false;
    authFetch('/auth/me')
      .then((response) => {
        if (!cancelled) setVerified(response.ok ? 'valid' : 'invalid');
      })
      .catch(() => {
        if (!cancelled) setVerified('invalid');
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (verified === 'checking') {
    return null;
  }

  if (verified === 'valid') {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
