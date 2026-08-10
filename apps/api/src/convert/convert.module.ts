import { Module } from '@nestjs/common';
import { QuotaModule } from '../quota/quota.module';
import { ConvertController } from './convert.controller';
import { ConvertService } from './convert.service';

@Module({
  imports: [QuotaModule],
  controllers: [ConvertController],
  providers: [ConvertService],
})
export class ConvertModule {}
