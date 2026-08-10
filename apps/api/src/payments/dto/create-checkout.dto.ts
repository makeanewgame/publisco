import { IsIn, IsOptional } from 'class-validator';

export class CreateCheckoutDto {
  // Frontend'in aktif dili; Lemon Squeezy checkout'unun dilini belirler
  // (verilmezse mağaza varsayılanına, sonra tarayıcı diline düşer).
  @IsOptional()
  @IsIn(['tr', 'en'])
  locale?: 'tr' | 'en';
}
