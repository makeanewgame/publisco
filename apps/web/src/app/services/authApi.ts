import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import { API_BASE_URL } from '../../lib/apiConfig';

export interface AuthUser {
  id: string;
  email: string;
  name?: string;
  avatarUrl?: string;
  emailVerified: boolean;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export interface SignUpResponse {
  // E-posta doğrulanana kadar oturum açılmaz, bu yüzden burada token yoktur —
  // token'lar verifyEmail başarılı olunca döner.
  user: AuthUser;
}

export interface VerifyEmailResponse {
  user: AuthUser;
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export interface SignInResponse {
  user: AuthUser;
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export const authApi = createApi({
  reducerPath: 'authApi',
  baseQuery: fetchBaseQuery({ baseUrl: API_BASE_URL }),
  endpoints: (builder) => ({
    signUp: builder.mutation<
      SignUpResponse,
      { email: string; password: string; name?: string; locale?: 'tr' | 'en' }
    >({
      query: (credentials) => ({
        url: '/auth/sign-up',
        method: 'POST',
        body: credentials,
      }),
    }),
    signIn: builder.mutation<SignInResponse, { email: string; password: string }>({
      query: (credentials) => ({
        url: '/auth/sign-in',
        method: 'POST',
        body: credentials,
      }),
    }),
    googleAuth: builder.mutation<SignInResponse, { idToken: string; locale?: 'tr' | 'en' }>({
      query: (body) => ({
        url: '/auth/google',
        method: 'POST',
        body,
      }),
    }),
    signOut: builder.mutation<{ success: boolean }, { refreshToken: string }>({
      query: (body) => ({
        url: '/auth/sign-out',
        method: 'POST',
        body,
      }),
    }),
    forgotPassword: builder.mutation<{ success: boolean }, { email: string }>({
      query: (body) => ({
        url: '/auth/forgot-password',
        method: 'POST',
        body,
      }),
    }),
    resetPassword: builder.mutation<{ success: boolean }, { token: string; newPassword: string }>({
      query: (body) => ({
        url: '/auth/reset-password',
        method: 'POST',
        body,
      }),
    }),
    verifyEmail: builder.mutation<VerifyEmailResponse, { email: string; code: string }>({
      query: (body) => ({
        url: '/auth/verify-email',
        method: 'POST',
        body,
      }),
    }),
    resendVerification: builder.mutation<{ success: boolean }, { email: string }>({
      query: (body) => ({
        url: '/auth/resend-verification',
        method: 'POST',
        body,
      }),
    }),
  }),
});

export const {
  useSignUpMutation,
  useSignInMutation,
  useGoogleAuthMutation,
  useSignOutMutation,
  useForgotPasswordMutation,
  useResetPasswordMutation,
  useVerifyEmailMutation,
  useResendVerificationMutation,
} = authApi;
