import {
  Controller,
  Get,
  Headers,
  Post,
  RawBodyRequest,
  Req,
  UnauthorizedException,
  UseGuards,
} from '@nestjs/common';
import type { Request } from 'express';
import { CurrentUser, RequestUser } from '../auth/decorators/current-user.decorator';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { PaymentsService } from './payments.service';

@Controller('payments')
export class PaymentsController {
  constructor(private readonly paymentsService: PaymentsService) {}

  @UseGuards(JwtAuthGuard)
  @Post('checkout')
  async createCheckout(@CurrentUser() user: RequestUser) {
    const url = await this.paymentsService.createCheckoutUrl(user);
    return { url };
  }

  @UseGuards(JwtAuthGuard)
  @Get('subscription')
  getSubscription(@CurrentUser() user: RequestUser) {
    return this.paymentsService.getSubscriptionSummary(user.userId);
  }

  @UseGuards(JwtAuthGuard)
  @Post('subscription/cancel')
  cancelSubscription(@CurrentUser() user: RequestUser) {
    return this.paymentsService.cancelSubscription(user.userId);
  }

  @UseGuards(JwtAuthGuard)
  @Post('subscription/resume')
  resumeSubscription(@CurrentUser() user: RequestUser) {
    return this.paymentsService.resumeSubscription(user.userId);
  }

  @UseGuards(JwtAuthGuard)
  @Get('invoices')
  listInvoices(@CurrentUser() user: RequestUser) {
    return this.paymentsService.listInvoices(user.userId);
  }

  // Lemon Squeezy tarafından çağrılır, oturum gerektirmez — bunun yerine
  // X-Signature imzası (ham gövde üzerinden HMAC) doğrulanır.
  @Post('webhook')
  async handleWebhook(@Req() req: RawBodyRequest<Request>, @Headers('x-signature') signature?: string) {
    if (!req.rawBody || !this.paymentsService.verifyWebhookSignature(req.rawBody, signature)) {
      throw new UnauthorizedException('Invalid webhook signature.');
    }
    const payload = JSON.parse(req.rawBody.toString('utf8'));
    await this.paymentsService.handleWebhookEvent(payload);
    return { received: true };
  }
}
