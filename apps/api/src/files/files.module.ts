import { Module } from '@nestjs/common';
import { QuotaModule } from '../quota/quota.module';
import { FilesController } from './files.controller';
import { FilesService } from './files.service';

@Module({
  imports: [QuotaModule],
  controllers: [FilesController],
  providers: [FilesService],
})
export class FilesModule {}
