import { IsIn, IsOptional, IsString } from 'class-validator';

export class GoogleAuthDto {
  // Google Identity Services'in istemci tarafında (web/mobile) ürettiği ID token.
  @IsString()
  idToken!: string;

  // Frontend'in aktif dili; hesap ilk kez oluşturuluyorsa e-posta dilini belirler.
  @IsOptional()
  @IsIn(['tr', 'en'])
  locale?: 'tr' | 'en';
}
