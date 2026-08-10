import {
  Body,
  Controller,
  Get,
  Param,
  Post,
  Res,
  StreamableFile,
  UploadedFile,
  UseGuards,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import type { Response } from 'express';
import { CurrentUser, RequestUser } from '../auth/decorators/current-user.decorator';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { ConvertService } from './convert.service';
import { ConvertPdfDto } from './dto/convert-pdf.dto';

const MAX_UPLOAD_BYTES = 100 * 1024 * 1024; // 100 MB

@UseGuards(JwtAuthGuard)
@Controller('convert')
export class ConvertController {
  constructor(private readonly convertService: ConvertService) {}

  // Dönüştürmeyi hemen başlatmak yerine bir job kuyruğa alır ve job id döner;
  // istemci ilerlemeyi GET :jobId/status ile poll'lar, bitince GET :jobId/result
  // ile dosyayı indirir (bkz. apps/worker/app/jobs.py — worker tarafı da aynı akışta).
  @Post()
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: MAX_UPLOAD_BYTES } }))
  async convert(
    @UploadedFile() file: Express.Multer.File,
    @Body() dto: ConvertPdfDto,
    @CurrentUser() user: RequestUser,
  ) {
    return this.convertService.convert(user.userId, file, dto);
  }

  @Get(':jobId/status')
  async status(@Param('jobId') jobId: string, @CurrentUser() user: RequestUser) {
    return this.convertService.getStatus(user.userId, jobId);
  }

  @Get(':jobId/result')
  async result(
    @Param('jobId') jobId: string,
    @CurrentUser() user: RequestUser,
    @Res({ passthrough: true }) res: Response,
  ) {
    const result = await this.convertService.getResult(user.userId, jobId);

    res.set({
      'Content-Type': 'application/epub+zip',
      'Content-Length': result.buffer.length,
      'Content-Disposition': `attachment; filename="${result.fileName}"`,
    });

    return new StreamableFile(result.buffer);
  }
}
