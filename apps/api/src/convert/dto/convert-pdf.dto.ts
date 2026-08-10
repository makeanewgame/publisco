import { Transform } from 'class-transformer';
import { IsBoolean, IsOptional, IsString, MaxLength } from 'class-validator';

export class ConvertPdfDto {
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
