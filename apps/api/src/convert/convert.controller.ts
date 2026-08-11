import { Body, Controller, Get, Param, Post, Res, StreamableFile, UseGuards } from '@nestjs/common';
import type { Response } from 'express';
import { CurrentUser, RequestUser } from '../auth/decorators/current-user.decorator';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { ConvertService } from './convert.service';
import { AnalyzePdfDto } from './dto/analyze-pdf.dto';
import { ConvertPdfDto } from './dto/convert-pdf.dto';
import { RequestConvertUploadDto } from './dto/request-upload.dto';

@Controller('convert')
export class ConvertController {
  constructor(private readonly convertService: ConvertService) {}

  // Client, dosyayı buraya değil doğrudan Vercel Blob'a yükleyeceği için önce
  // bunun için tek kullanımlık, süreli bir upload token'ı ister (bkz.
  // ConvertService.createUploadToken — auth + kaba kota kontrolü burada yapılır).
  @UseGuards(JwtAuthGuard)
  @Post('upload-url')
  async createUploadUrl(@Body() dto: RequestConvertUploadDto, @CurrentUser() user: RequestUser) {
    return this.convertService.createUploadToken(user.userId, dto.fileName);
  }

  // `/analyze`'ın kendi, ayrı upload token'ı (bkz. createAnalyzeUploadToken) —
  // kullanıcıya/kotaya bağlı değil, bu yüzden auth GEREKTİRMİYOR (kullanıcı
  // dosya seçtiğinde henüz giriş yapmamış olabilir).
  @Post('analyze/upload-url')
  async createAnalyzeUploadUrl(@Body() dto: RequestConvertUploadDto) {
    return this.convertService.createAnalyzeUploadToken(dto.fileName);
  }

  // Dosya seçilir seçilmez (dönüşümden önce, kullanıcı henüz giriş yapmamış
  // olabilir — bkz. ConvertPage.tsx'teki 'auto' mod) başlık/yazar/bölüm
  // tahmini için çağrılır. Client dosyayı `analyze/upload-url`'den aldığı
  // token'la doğrudan Blob'a yükledi, burada sadece `dto.pathname` gelir —
  // `/convert`'teki gibi dosya bu isteğin gövdesine hiç girmiyor (bkz.
  // ConvertService.analyze; eskiden multipart proxy'ydi, PDF client'tan bu
  // endpoint'e bayt olarak geliyordu ve Vercel Function'ın ~4.5MB inbound
  // body limitine takılıp 503 üretiyordu). Kota/kullanıcıya özel bir yan
  // etkisi yok, bu yüzden bilinçli olarak auth GEREKTİRMİYOR — JwtAuthGuard
  // eklenirse henüz giriş yapmamış kullanıcılar dosya seçer seçmez 401 alır.
  @Post('analyze')
  async analyze(@Body() dto: AnalyzePdfDto) {
    return this.convertService.analyze(dto.pathname);
  }

  // Dönüştürmeyi hemen başlatmak yerine Modal'a bir job devreder ve job id
  // döner; istemci ilerlemeyi GET :jobId/status ile poll'lar, bitince
  // GET :jobId/result ile dosyayı indirir (bkz. modal_worker/main.py —
  // Modal tarafı da aynı akışta). Dosyanın kendisi bu isteğin gövdesinde
  // değil — client onu `upload-url`den aldığı token'la doğrudan Blob'a
  // yükledi, burada sadece `dto.pathname` gelir (bkz. ConvertService.resolveUploadedBlob).
  @UseGuards(JwtAuthGuard)
  @Post()
  async convert(@Body() dto: ConvertPdfDto, @CurrentUser() user: RequestUser) {
    return this.convertService.convert(user.userId, dto);
  }

  @UseGuards(JwtAuthGuard)
  @Get(':jobId/status')
  async status(@Param('jobId') jobId: string, @CurrentUser() user: RequestUser) {
    return this.convertService.getStatus(user.userId, jobId);
  }

  @UseGuards(JwtAuthGuard)
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
