// Dev'de Vite `/api` isteklerini backend:3001'e proxy'ler (bkz. vite.config.ts),
// bu yüzden varsayılan relative — localhost dışı bir deploy'da da kırılmaz.
// Worker (3002) proxy'lenmiyor, o yüzden onun için mutlak bir varsayılan gerekiyor.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';
export const WORKER_URL = import.meta.env.VITE_WORKER_URL ?? 'http://127.0.0.1:3002';
