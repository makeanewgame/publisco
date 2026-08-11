// Dev'de Vite `/api` isteklerini backend:3001'e proxy'ler (bkz. vite.config.ts),
// bu yüzden varsayılan relative — localhost dışı bir deploy'da da kırılmaz.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';
