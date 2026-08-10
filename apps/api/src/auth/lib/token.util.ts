import { createHash, randomBytes, randomInt } from 'crypto';

// jsonwebtoken'ın expiresIn'in kabul ettiği kısa süre formatı ('15m', '7d', ...).
export type Duration = `${number}${'ms' | 's' | 'm' | 'h' | 'd'}`;

export function generateRawToken(): string {
  return randomBytes(32).toString('hex');
}

// E-posta doğrulaması gibi kullanıcının elle gireceği akışlar için
// kriptografik olarak güvenli, 6 haneli sayısal kod üretir (ör. "042817").
export function generateNumericCode(length = 6): string {
  const max = 10 ** length;
  return randomInt(0, max).toString().padStart(length, '0');
}

// Ham token'lar hiçbir zaman veritabanına yazılmaz; sadece hash'i saklanır.
export function hashToken(token: string): string {
  return createHash('sha256').update(token).digest('hex');
}

const UNIT_TO_MS: Record<string, number> = {
  ms: 1,
  s: 1000,
  m: 60 * 1000,
  h: 60 * 60 * 1000,
  d: 24 * 60 * 60 * 1000,
};

// '15m' / '7d' gibi @nestjs/jwt expiresIn formatını milisaniyeye çevirir,
// böylece refresh token kaydının expiresAt alanı JWT süresiyle senkron kalır.
export function msFromDuration(duration: string): number {
  const match = /^(\d+)(ms|s|m|h|d)?$/.exec(duration.trim());
  if (!match) {
    throw new Error(`Geçersiz süre formatı: ${duration}`);
  }
  const value = Number(match[1]);
  const unit = match[2] ?? 'ms';
  return value * UNIT_TO_MS[unit];
}
