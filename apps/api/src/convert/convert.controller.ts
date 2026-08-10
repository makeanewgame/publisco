import { Body, Controller, Get, Param, Post, Res, StreamableFile, UseGuards } from '@nestjs/common';
import type { Response } from 'express';
import { CurrentUser, RequestUser } from '../auth/decorators/current-user.decorator';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { ConvertService } from './convert.service';
import { ConvertPdfDto } from './dto/convert-pdf.dto';
import { RequestConvertUploadDto } from './dto/request-upload.dto';

@UseGuards(JwtAuthGuard)
@Controller('convert')
export class ConvertController {
  constructor(private readonly convertService: ConvertService) {}

  // Client, dosyayı buraya değil doğrudan Vercel Blob'a yükleyeceği için önce
  // bunun için tek kullanımlık, süreli bir upload token'ı ister (bkz.
  // ConvertService.createUploadToken — auth + kaba kota kontrolü burada yapılır).
  @Post('upload-url')
  async createUploadUrl(@Body() dto: RequestConvertUploadDto, @CurrentUser() user: RequestUser) {
    return this.convertService.createUploadToken(user.userId, dto.fileName);
  }

  // Dönüştürmeyi hemen başlatmak yerine bir job kuyruğa alır ve job id döner;
  // istemci ilerlemeyi GET :jobId/status ile poll'lar, bitince GET :jobId/result
  // ile dosyayı indirir (bkz. apps/worker/app/jobs.py — worker tarafı da aynı akışta).
  // Dosyanın kendisi bu isteğin gövdesinde değil — client onu `upload-url`den
  // aldığı token'la doğrudan Blob'a yükledi, burada sadece `dto.pathname` gelir
  // (bkz. ConvertService.consumeUploadedBlob).
  @Post()
  async convert(@Body() dto: ConvertPdfDto, @CurrentUser() user: RequestUser) {
    return this.convertService.convert(user.userId, dto);
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
