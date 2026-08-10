import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Patch,
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
import { RenameFileDto } from './dto/rename-file.dto';
import { FilesService } from './files.service';

const MAX_UPLOAD_BYTES = 100 * 1024 * 1024; // 100 MB

@UseGuards(JwtAuthGuard)
@Controller('files')
export class FilesController {
  constructor(private readonly filesService: FilesService) {}

  @Post()
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: MAX_UPLOAD_BYTES } }))
  upload(@UploadedFile() file: Express.Multer.File, @CurrentUser() user: RequestUser) {
    return this.filesService.upload(user.userId, file);
  }

  @Get()
  list(@CurrentUser() user: RequestUser) {
    return this.filesService.list(user.userId);
  }

  @Get(':id/download')
  async download(
    @Param('id') id: string,
    @CurrentUser() user: RequestUser,
    @Res({ passthrough: true }) res: Response,
  ) {
    const { stream, contentType, size, fileName } = await this.filesService.getDownloadPayload(
      user.userId,
      id,
    );

    res.set({
      'Content-Type': contentType,
      'Content-Length': size,
      'Content-Disposition': `attachment; filename="${fileName}"`,
    });

    return new StreamableFile(stream);
  }

  @Patch(':id')
  rename(
    @Param('id') id: string,
    @Body() dto: RenameFileDto,
    @CurrentUser() user: RequestUser,
  ) {
    return this.filesService.rename(user.userId, id, dto.fileName);
  }

  @Delete(':id')
  remove(@Param('id') id: string, @CurrentUser() user: RequestUser) {
    return this.filesService.remove(user.userId, id);
  }
}
