import { ValidationPipe } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  // rawBody: Lemon Squeezy webhook imzası (X-Signature) ham istek gövdesi
  // üzerinden hesaplanır; Nest bunu req.rawBody olarak sunar, JSON body
  // parse'ı ayrıca normal şekilde çalışmaya devam eder.
  const app = await NestFactory.create(AppModule, { rawBody: true });
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
