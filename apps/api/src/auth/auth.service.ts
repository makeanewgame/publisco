import { randomUUID } from 'crypto';
import { ConflictException, Injectable, NotFoundException, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { OAuth2Client } from 'google-auth-library';
import { AuthProvider } from '../generated/prisma/client';
import { MailService } from '../mail/mail.service';
import { resolveMailLocale } from '../mail/mail.templates';
import { PrismaService } from '../prisma/prisma.service';
import { UsersService } from '../users/users.service';
import { ForgotPasswordDto } from './dto/forgot-password.dto';
import { GoogleAuthDto } from './dto/google-auth.dto';
import { ResendVerificationDto } from './dto/resend-verification.dto';
import { ResetPasswordDto } from './dto/reset-password.dto';
import { SignInDto } from './dto/sign-in.dto';
import { SignUpDto } from './dto/sign-up.dto';
import { VerifyEmailDto } from './dto/verify-email.dto';
import { AuthTokens } from './interfaces/auth-tokens.interface';
import { Duration, generateNumericCode, generateRawToken, hashToken, msFromDuration } from './lib/token.util';

const EMAIL_VERIFICATION_TTL_MS = 15 * 60 * 1000;
const MAX_VERIFICATION_ATTEMPTS = 5;
const PASSWORD_RESET_TTL_MS = 60 * 60 * 1000;
const BCRYPT_ROUNDS = 12;

@Injectable()
export class AuthService {
  private readonly googleClient: OAuth2Client;

  constructor(
    private readonly prisma: PrismaService,
    private readonly usersService: UsersService,
    private readonly mailService: MailService,
    private readonly jwtService: JwtService,
    private readonly config: ConfigService,
  ) {
    this.googleClient = new OAuth2Client(this.config.get<string>('GOOGLE_CLIENT_ID'));
  }

  async signUp(dto: SignUpDto) {
    const existing = await this.usersService.findByEmail(dto.email);
    if (existing) {
      throw new ConflictException('Bu e-posta adresi zaten kayıtlı.');
    }

    const passwordHash = await bcrypt.hash(dto.password, BCRYPT_ROUNDS);
    const user = await this.usersService.createLocalUser({
      email: dto.email,
      passwordHash,
      name: dto.name,
      locale: resolveMailLocale(dto.locale),
    });

    await this.issueEmailVerificationToken(user.id, user.email, user.locale);

    // E-posta doğrulanmadan oturum açılmaz: token burada verilmez,
    // hesap ancak verifyEmail başarılı olunca giriş yapabilir hale gelir.
    return { user: this.toPublicUser(user) };
  }

  async signIn(dto: SignInDto) {
    const user = await this.usersService.findByEmail(dto.email);
    if (!user || !user.passwordHash) {
      throw new UnauthorizedException('E-posta veya şifre hatalı.');
    }

    const passwordMatches = await bcrypt.compare(dto.password, user.passwordHash);
    if (!passwordMatches) {
      throw new UnauthorizedException('E-posta veya şifre hatalı.');
    }

    const tokens = await this.issueTokens(user.id, user.email);
    return { user: this.toPublicUser(user), ...tokens };
  }

  async signOut(refreshToken: string) {
    const tokenHash = hashToken(refreshToken);
    await this.prisma.refreshToken.updateMany({
      where: { tokenHash, revokedAt: null },
      data: { revokedAt: new Date() },
    });
    return { success: true };
  }

  // Google için ayrı "sign in" / "sign up" uçları yok: ID token doğrulanır,
  // hesap varsa oturum açılır, yoksa otomatik oluşturulur (find-or-create).
  async googleAuth(dto: GoogleAuthDto) {
    const clientId = this.config.get<string>('GOOGLE_CLIENT_ID');
    if (!clientId) {
      throw new UnauthorizedException('Google girişi yapılandırılmamış.');
    }

    const ticket = await this.googleClient.verifyIdToken({
      idToken: dto.idToken,
      audience: clientId,
    });
    const payload = ticket.getPayload();
    if (!payload?.email) {
      throw new UnauthorizedException('Geçersiz Google kimlik doğrulaması.');
    }

    let user = await this.usersService.findByGoogleId(payload.sub);

    if (!user) {
      const existingByEmail = await this.usersService.findByEmail(payload.email);
      user = existingByEmail
        ? await this.usersService.linkGoogleAccount(existingByEmail.id, payload.sub, payload.picture)
        : await this.usersService.createGoogleUser({
            email: payload.email,
            googleId: payload.sub,
            name: payload.name,
            avatarUrl: payload.picture,
            locale: resolveMailLocale(dto.locale),
          });
    }

    const tokens = await this.issueTokens(user.id, user.email);
    return { user: this.toPublicUser(user), ...tokens };
  }

  async forgotPassword(dto: ForgotPasswordDto) {
    const user = await this.usersService.findByEmail(dto.email);
    if (!user) {
      throw new NotFoundException('Bu e-posta adresiyle kayıtlı bir hesap bulunamadı.');
    }
    if (!user.passwordHash) {
      throw new UnauthorizedException('Bu hesap Google ile oluşturulmuş, şifre sıfırlama yapılamaz.');
    }

    const rawToken = generateRawToken();
    await this.prisma.passwordResetToken.create({
      data: {
        userId: user.id,
        tokenHash: hashToken(rawToken),
        expiresAt: new Date(Date.now() + PASSWORD_RESET_TTL_MS),
      },
    });
    await this.mailService.sendPasswordResetEmail(user.email, rawToken, resolveMailLocale(user.locale));
    return { success: true };
  }

  async resetPassword(dto: ResetPasswordDto) {
    const tokenHash = hashToken(dto.token);
    const resetToken = await this.prisma.passwordResetToken.findUnique({ where: { tokenHash } });

    if (!resetToken || resetToken.consumedAt || resetToken.expiresAt < new Date()) {
      throw new UnauthorizedException('Sıfırlama bağlantısı geçersiz veya süresi dolmuş.');
    }

    const passwordHash = await bcrypt.hash(dto.newPassword, BCRYPT_ROUNDS);

    await this.prisma.$transaction([
      this.prisma.user.update({
        where: { id: resetToken.userId },
        data: { passwordHash },
      }),
      this.prisma.passwordResetToken.update({
        where: { id: resetToken.id },
        data: { consumedAt: new Date() },
      }),
      // Şifre değiştiğinde tüm cihazlardaki oturumlar iptal edilir.
      this.prisma.refreshToken.updateMany({
        where: { userId: resetToken.userId, revokedAt: null },
        data: { revokedAt: new Date() },
      }),
    ]);

    return { success: true };
  }

  async verifyEmail(dto: VerifyEmailDto) {
    const user = await this.usersService.findByEmail(dto.email);
    if (!user) {
      throw new UnauthorizedException('Kod geçersiz veya süresi dolmuş.');
    }

    const verificationToken = await this.prisma.emailVerificationToken.findFirst({
      where: { userId: user.id, consumedAt: null, expiresAt: { gt: new Date() } },
      orderBy: { createdAt: 'desc' },
    });

    if (!verificationToken) {
      throw new UnauthorizedException('Kod geçersiz veya süresi dolmuş.');
    }

    if (verificationToken.attempts >= MAX_VERIFICATION_ATTEMPTS) {
      throw new UnauthorizedException('Çok fazla hatalı deneme. Yeni bir kod iste.');
    }

    if (verificationToken.tokenHash !== hashToken(dto.code)) {
      await this.prisma.emailVerificationToken.update({
        where: { id: verificationToken.id },
        data: { attempts: { increment: 1 } },
      });
      throw new UnauthorizedException('Kod hatalı.');
    }

    await this.prisma.$transaction([
      this.prisma.user.update({
        where: { id: user.id },
        data: { emailVerified: true },
      }),
      this.prisma.emailVerificationToken.update({
        where: { id: verificationToken.id },
        data: { consumedAt: new Date() },
      }),
    ]);

    // Doğrulama tamamlandığında oturum burada açılır: sign-up sırasında
    // verilmeyen token'lar artık üretilip döndürülür.
    const tokens = await this.issueTokens(user.id, user.email);
    return {
      user: this.toPublicUser({ ...user, emailVerified: true }),
      ...tokens,
    };
  }

  async resendVerificationCode(dto: ResendVerificationDto) {
    const user = await this.usersService.findByEmail(dto.email);
    // Hesabın var olup olmadığını sızdırmamak için her durumda aynı yanıt dönülür.
    if (user && !user.emailVerified) {
      await this.issueEmailVerificationToken(user.id, user.email, user.locale);
    }
    return { success: true };
  }

  async refreshTokens(refreshToken: string): Promise<AuthTokens> {
    let payload: { sub: string; email: string };
    try {
      payload = await this.jwtService.verifyAsync(refreshToken, {
        secret: this.config.get<string>('JWT_REFRESH_SECRET'),
      });
    } catch {
      throw new UnauthorizedException('Oturum süresi dolmuş, tekrar giriş yapın.');
    }

    const tokenHash = hashToken(refreshToken);
    const stored = await this.prisma.refreshToken.findUnique({ where: { tokenHash } });

    if (!stored || stored.revokedAt || stored.expiresAt < new Date()) {
      throw new UnauthorizedException('Oturum süresi dolmuş, tekrar giriş yapın.');
    }

    // Rotasyon: kullanılan refresh token iptal edilip yenisi verilir.
    await this.prisma.refreshToken.update({
      where: { id: stored.id },
      data: { revokedAt: new Date() },
    });

    return this.issueTokens(payload.sub, payload.email);
  }

  private async issueEmailVerificationToken(
    userId: string,
    email: string,
    locale?: string,
  ): Promise<string> {
    const code = generateNumericCode();
    await this.prisma.$transaction([
      // Önceki kullanılmamış kodları geçersiz kılar, böylece eski bir kodla
      // deneme yapılamaz ve tek bir aktif kod kalır.
      this.prisma.emailVerificationToken.updateMany({
        where: { userId, consumedAt: null },
        data: { consumedAt: new Date() },
      }),
      this.prisma.emailVerificationToken.create({
        data: {
          userId,
          tokenHash: hashToken(code),
          expiresAt: new Date(Date.now() + EMAIL_VERIFICATION_TTL_MS),
        },
      }),
    ]);
    await this.mailService.sendVerificationEmail(email, code, resolveMailLocale(locale));
    return code;
  }

  private async issueTokens(userId: string, email: string): Promise<AuthTokens> {
    // jti olmadan aynı saniye içinde üretilen JWT'ler (aynı sub/email/iat/exp)
    // birebir aynı string olur; refresh token'ın unique tokenHash'i bu yüzden çakışabilir.
    const payload = { sub: userId, email, jti: randomUUID() };

    const accessToken = await this.jwtService.signAsync(payload, {
      secret: this.config.get<string>('JWT_ACCESS_SECRET'),
      expiresIn: this.config.get<Duration>('JWT_ACCESS_EXPIRES_IN', '15m' as Duration),
    });

    const refreshExpiresIn = this.config.get<Duration>(
      'JWT_REFRESH_EXPIRES_IN',
      '7d' as Duration,
    );
    const refreshToken = await this.jwtService.signAsync(payload, {
      secret: this.config.get<string>('JWT_REFRESH_SECRET'),
      expiresIn: refreshExpiresIn,
    });

    await this.prisma.refreshToken.create({
      data: {
        userId,
        tokenHash: hashToken(refreshToken),
        expiresAt: new Date(Date.now() + msFromDuration(refreshExpiresIn)),
      },
    });

    return { accessToken, refreshToken };
  }

  private toPublicUser(user: {
    id: string;
    email: string;
    name: string | null;
    avatarUrl: string | null;
    emailVerified: boolean;
    provider: AuthProvider;
  }) {
    return {
      id: user.id,
      email: user.email,
      name: user.name,
      avatarUrl: user.avatarUrl,
      emailVerified: user.emailVerified,
      provider: user.provider,
    };
  }
}
