import { IsNotEmpty, IsString, MaxLength } from 'class-validator';

export class AnalyzePdfDto {
  // `POST /convert/analyze/upload-url`'den alınan token ile client tarafından
  // doğrudan Vercel Blob'a yüklenen geçici PDF'in pathname'i (bkz.
  // ConvertService.createAnalyzeUploadToken).
  @IsString()
  @IsNotEmpty()
  @MaxLength(1024)
  pathname!: string;
}
