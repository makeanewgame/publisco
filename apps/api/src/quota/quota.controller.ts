import { Controller, Get, UseGuards } from '@nestjs/common';
import { CurrentUser, RequestUser } from '../auth/decorators/current-user.decorator';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { QuotaService } from './quota.service';

@UseGuards(JwtAuthGuard)
@Controller('quota')
export class QuotaController {
  constructor(private readonly quotaService: QuotaService) {}

  @Get()
  getMyQuota(@CurrentUser() user: RequestUser) {
    return this.quotaService.getUsageSummary(user.userId);
  }
}
