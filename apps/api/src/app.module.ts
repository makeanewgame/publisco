import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { AuthModule } from './auth/auth.module';
import { ConvertModule } from './convert/convert.module';
import { FilesModule } from './files/files.module';
import { MailModule } from './mail/mail.module';
import { PaymentsModule } from './payments/payments.module';
import { PrismaModule } from './prisma/prisma.module';
import { QuotaModule } from './quota/quota.module';
import { UsersModule } from './users/users.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    PrismaModule,
    MailModule,
    UsersModule,
    AuthModule,
    FilesModule,
    QuotaModule,
    ConvertModule,
    PaymentsModule,
  ],
  controllers: [],
  providers: [],
})
export class AppModule {}
