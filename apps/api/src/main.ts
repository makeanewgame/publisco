import { ValidationPipe } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  // rawBody: Lemon Squeezy webhook imzası (X-Signature) ham istek gövdesi
  // üzerinden hesaplanır; Nest bunu req.rawBody olarak sunar, JSON body
  // parse'ı ayrıca normal şekilde çalışmaya devam eder.
  const app = await NestFactory.create(AppModule, { rawBody: true });
  // Vercel'in kendi proxy'si arkasında çalışıyor — bu olmadan `req.ip` her
  // zaman Vercel'in dahili proxy adresine düşer, IP-bazlı rate limiting
  // (ThrottlerModule, bkz. AppModule) tüm kullanıcıları TEK bir IP altında
  // toplayıp gereğinden çok daha agresif limitler (ya da tam tersi, hiç ayrım
  // yapmayan bir limit) uygulamış olurdu.
  app.getHttpAdapter().getInstance().set('trust proxy', 1);
  app.enableCors();
  app.setGlobalPrefix('api');
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
    }),
  );
  await app.listen(3001);
}
bootstrap();
