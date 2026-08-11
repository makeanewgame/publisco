import { Module } from '@nestjs/common';
import { QuotaModule } from '../quota/quota.module';
import { ConvertController } from './convert.controller';
import { ConvertService } from './convert.service';
import { ModalWebhookController } from './modal-webhook.controller';

@Module({
  imports: [QuotaModule],
  controllers: [ConvertController, ModalWebhookController],
  providers: [ConvertService],
})
export class ConvertModule {}
