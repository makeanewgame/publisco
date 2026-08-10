import { IsEmail, IsIn, IsOptional, IsString, Matches, MinLength } from 'class-validator';

export class SignUpDto {
  @IsEmail()
  email!: string;

  // Frontend'in aktif dili; e-posta doğrulama şablonunun dilini belirler.
  @IsOptional()
  @IsIn(['tr', 'en'])
  locale?: 'tr' | 'en';

  @IsString()
  @MinLength(8, { message: 'Şifre en az 8 karakter olmalıdır.' })
  @Matches(/(?=.*[a-z])/, { message: 'Şifre en az bir küçük harf içermelidir.' })
  @Matches(/(?=.*[A-Z])/, { message: 'Şifre en az bir büyük harf içermelidir.' })
  @Matches(/(?=.*[!"#$%&'()*+,\-./:;<=>?@[\]^_`{|}~])/, {
    message: 'Şifre en az bir noktalama işareti içermelidir.',
  })
  password!: string;

  @IsOptional()
  @IsString()
  name?: string;
}
