import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { AuthUser } from './services/authApi';

interface AuthState {
  user: AuthUser | null;
}

function loadUserFromStorage(): AuthUser | null {
  const userData = localStorage.getItem('user');
  return userData ? JSON.parse(userData) : null;
}

const initialState: AuthState = {
  user: loadUserFromStorage(),
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    setCredentials(
      state,
      action: PayloadAction<{ user: AuthUser; accessToken: string; refreshToken: string }>,
    ) {
      state.user = action.payload.user;
      localStorage.setItem('accessToken', action.payload.accessToken);
      localStorage.setItem('refreshToken', action.payload.refreshToken);
      localStorage.setItem('user', JSON.stringify(action.payload.user));
    },
    clearCredentials(state) {
      state.user = null;
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');
      localStorage.removeItem('user');
    },
  },
});

export const { setCredentials, clearCredentials } = authSlice.actions;
export default authSlice.reducer;

export const selectCurrentUser = (state: { auth: AuthState }) => state.auth.user;
