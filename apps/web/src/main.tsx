import React from 'react';
import ReactDOM from 'react-dom/client';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { Provider } from 'react-redux';
import { BrowserRouter } from 'react-router-dom';
import { PersistGate } from 'redux-persist/integration/react';
import App from './App';
import { store, persistor } from './app/store';
import { LocaleProvider, useLocale } from './i18n';
import { ThemeProvider } from './theme';
import './index.css';

const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? '';

function LocalizedGoogleOAuthProvider({ children }: { children: React.ReactNode }) {
  const { locale } = useLocale();

  return (
    <GoogleOAuthProvider key={locale} clientId={googleClientId} locale={locale}>
      {children}
    </GoogleOAuthProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Provider store={store}>
      <PersistGate loading={null} persistor={persistor}>
        <BrowserRouter>
          <ThemeProvider>
            <LocaleProvider>
              <LocalizedGoogleOAuthProvider>
                <App />
              </LocalizedGoogleOAuthProvider>
            </LocaleProvider>
          </ThemeProvider>
        </BrowserRouter>
      </PersistGate>
    </Provider>
  </React.StrictMode>,
);
