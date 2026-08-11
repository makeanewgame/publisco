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
import { RequestConvertUploadDto } from './dto/request-upload.dto';

const MAX_ANALYZE_UPLOAD_BYTES = 100 * 1024 * 1024; // 100 MB — createUploadToken'daki convert limitiyle aynı

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

  // Dosya seçilir seçilmez (dönüşümden önce) başlık/yazar/bölüm tahmini için
  // çağrılır — Modal'ın `/analyze` endpoint'ine multipart proxy (bkz.
  // ConvertService.analyze). Eskiden worker'a doğrudan, kimlik doğrulamasız
  // gidiyordu; artık backend üzerinden proxy'lendiği için JWT gerektiriyor.
  @Post('analyze')
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: MAX_ANALYZE_UPLOAD_BYTES } }))
  async analyze(@UploadedFile() file: Express.Multer.File) {
    return this.convertService.analyze(file);
  }

  // Dönüştürmeyi hemen başlatmak yerine Modal'a bir job devreder ve job id
  // döner; istemci ilerlemeyi GET :jobId/status ile poll'lar, bitince
  // GET :jobId/result ile dosyayı indirir (bkz. modal_worker/main.py —
  // Modal tarafı da aynı akışta). Dosyanın kendisi bu isteğin gövdesinde
  // değil — client onu `upload-url`den aldığı token'la doğrudan Blob'a
  // yükledi, burada sadece `dto.pathname` gelir (bkz. ConvertService.resolveUploadedBlob).
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
