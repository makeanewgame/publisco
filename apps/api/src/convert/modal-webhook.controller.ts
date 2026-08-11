import { Controller, Headers, Post, RawBodyRequest, Req, UnauthorizedException } from '@nestjs/common';
import type { Request } from 'express';
import { ConvertService } from './convert.service';

// Modal'ın `run_pipeline` fonksiyonu (bkz. modal_worker/main.py) dönüştürme
// tamamlandığında/başarısız olduğunda bu uca POST atar — oturum gerektirmez,
// bunun yerine X-Signature imzası (ham gövde üzerinden HMAC) doğrulanır.
// `payments.controller.ts`'teki Lemon Squeezy webhook deseniyle birebir aynı.
@Controller('webhooks')
export class ModalWebhookController {
  constructor(private readonly convertService: ConvertService) {}

  @Post('modal-result')
  async handleWebhook(@Req() req: RawBodyRequest<Request>, @Headers('x-signature') signature?: string) {
    if (!req.rawBody || !this.convertService.verifyModalWebhookSignature(req.rawBody, signature)) {
      throw new UnauthorizedException('Invalid webhook signature.');
    }
    const payload = JSON.parse(req.rawBody.toString('utf8'));
    await this.convertService.handleModalWebhook(payload);
    return { received: true };
  }
}
