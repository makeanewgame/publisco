import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD } from '@nestjs/core';
import { ThrottlerGuard, ThrottlerModule } from '@nestjs/throttler';
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
    // Genel varsayılan: IP başına dakikada 100 istek. Auth'suz/maliyetli
    // endpoint'ler (ör. ConvertController'daki /analyze) daha sıkı bir limiti
    // @Throttle(...) ile kendi üzerinde override ediyor — bkz. NOTES.md
    // (/analyze auth'suz + rate-limit'siz, maliyet DoS'u riski).
    ThrottlerModule.forRoot([{ ttl: 60_000, limit: 100 }]),
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
  providers: [{ provide: APP_GUARD, useClass: ThrottlerGuard }],
})
export class AppModule {}
