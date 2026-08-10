import { Route, Routes } from 'react-router-dom';
import { RootLayout } from './layouts/RootLayout';
import { MainLayout } from './layouts/MainLayout';
import { RequireAuth } from './routes/RequireAuth';
import { RequireGuest } from './routes/RequireGuest';
import HomePage from './pages/HomePage';
import ConvertPage from './pages/ConvertPage';
import LibraryPage from './pages/LibraryPage';
import PremiumPage from './pages/PremiumPage';
import AuthPage from './pages/AuthPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import PrivacyPolicyPage from './pages/PrivacyPolicyPage';
import TermsOfServicePage from './pages/TermsOfServicePage';

export default function App() {
  return (
    <Routes>
      <Route element={<RootLayout />}>
        <Route path="/" element={<HomePage />} />

        <Route element={<MainLayout />}>
          <Route path="/convert" element={<ConvertPage />} />
          <Route path="/premium" element={<PremiumPage />} />
          <Route path="/privacy-policy" element={<PrivacyPolicyPage />} />
          <Route path="/terms-of-service" element={<TermsOfServicePage />} />
          <Route element={<RequireAuth />}>
            <Route path="/library" element={<LibraryPage />} />
          </Route>
        </Route>

        <Route element={<RequireGuest />}>
          <Route path="/auth/signin" element={<AuthPage />} />
          <Route path="/auth/signup" element={<AuthPage />} />
        </Route>
        <Route path="/auth/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/auth/verify-email" element={<VerifyEmailPage />} />
      </Route>
    </Routes>
  );
}
