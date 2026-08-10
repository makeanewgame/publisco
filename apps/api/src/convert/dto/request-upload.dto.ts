import { IsNotEmpty, IsString, MaxLength } from 'class-validator';

export class RequestConvertUploadDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(255)
  fileName!: string;
}
