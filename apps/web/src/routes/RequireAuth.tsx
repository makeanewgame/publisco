import { useSelector } from 'react-redux';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { selectCurrentUser } from '../app/authSlice';

export function RequireAuth() {
  const user = useSelector(selectCurrentUser);
  const location = useLocation();

  if (!user) {
    return <Navigate to="/auth/signin" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
