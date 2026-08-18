import { HttpException, HttpStatus } from '@nestjs/common';

export interface QuotaExceededPayload {
  code: string;
  message: string;
  unit: 'bytes' | 'pages';
  used: number;
  limit: number;
  requested: number;
}

// Dönüşüm (converter) kotası dolduğunda atılır. Kullanıcı frontend'de
// premium'a yükseltme akışına yönlendirilmeli.
export class ConverterQuotaExceededException extends HttpException {
  constructor(usedPages: number, limitPages: number, requestedPages: number) {
    const payload: QuotaExceededPayload = {
      code: 'CONVERTER_QUOTA_EXCEEDED',
      message:
        'Dönüştürme kotanız doldu. Daha fazla dosya dönüştürmek için premium üyeliğe geçebilirsiniz.',
      unit: 'pages',
      used: usedPages,
      limit: limitPages,
      requested: requestedPages,
    };
    super(payload, HttpStatus.PAYMENT_REQUIRED);
  }
}

// Depolama kotası dolduğunda ya da dönüştürülecek dosya kalan alanı
// aştığında atılır. Kullanıcı depolama alanında yer açmaya yönlendirilmeli.
export class StorageQuotaExceededException extends HttpException {
  constructor(usedBytes: number, limitBytes: number, requestedBytes: number) {
    const payload: QuotaExceededPayload = {
      code: 'STORAGE_QUOTA_EXCEEDED',
      message:
        'Depolama alanınız yetersiz. Devam edebilmek için depolama alanınızda yer açın.',
      unit: 'bytes',
      used: usedBytes,
      limit: limitBytes,
      requested: requestedBytes,
    };
    super(payload, 507); // HttpStatus.INSUFFICIENT_STORAGE (WebDAV, RFC 4918) — bu Nest sürümünün enum'unda yok
  }
}
