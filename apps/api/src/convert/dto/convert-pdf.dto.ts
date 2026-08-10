import { Transform } from 'class-transformer';
import { IsBoolean, IsNotEmpty, IsOptional, IsString, MaxLength } from 'class-validator';

export class ConvertPdfDto {
  // `POST /convert/upload-url`'den alınan token ile client tarafından doğrudan
  // Vercel Blob'a yüklenen geçici PDF'in pathname'i (bkz. ConvertService.createUploadToken).
  @IsString()
  @IsNotEmpty()
  @MaxLength(1024)
  pathname!: string;

  // Blob pathname'i rastgele bir UUID içerdiği için orijinal dosya adı ayrıca taşınıyor
  // (worker'a iletilecek dosya adı ve başlık fallback'i için).
  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  fileName!: string;

  @IsOptional()
  @IsString()
  @MaxLength(255)
  title?: string;

  @IsOptional()
  @IsString()
  @MaxLength(255)
  author?: string;

  @IsOptional()
  @IsString()
  @MaxLength(10)
  language?: string;

  // book_config.json ile aynı şemadaki opsiyonel JSON ayarları; worker
  // tarafında pydantic ile doğrulanır, burada opak string olarak iletilir.
  @IsOptional()
  @IsString()
  options?: string;

  @IsOptional()
  @Transform(({ value }) => value === true || value === 'true')
  @IsBoolean()
  force_ocr?: boolean;
}
