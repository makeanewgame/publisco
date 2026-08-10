import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as nodemailer from 'nodemailer';
import {
  type MailLocale,
  passwordResetEmailTemplate,
  verificationEmailTemplate,
} from './mail.templates';

@Injectable()
export class MailService {
  private readonly logger = new Logger(MailService.name);
  private readonly transporter: nodemailer.Transporter | null;
  private readonly from: string;
  private readonly appUrl: string;

  constructor(private readonly config: ConfigService) {
    this.from = this.config.get<string>('MAIL_FROM', 'no-reply@publisco.local');
    this.appUrl = this.config.get<string>('APP_URL', 'http://localhost:5173');

    const host = this.config.get<string>('SMTP_HOST');
    const user = this.config.get<string>('SMTP_USER');

    this.transporter = host
      ? nodemailer.createTransport({
          host,
          port: this.config.get<number>('SMTP_PORT', 587),
          secure: this.config.get<string>('SMTP_SECURE', 'false') === 'true',
          auth: user
            ? { user, pass: this.config.get<string>('SMTP_PASS') }
            : undefined,
        })
      : null;
  }

  async sendVerificationEmail(to: string, code: string, locale: MailLocale = 'tr') {
    if (!this.transporter) {
      // SMTP henüz bağlanmadı: kodu okunaklı şekilde konsola basıyoruz ki
      // dev ortamında e-posta doğrulaması test edilebilsin.
      this.logger.warn(`[DEV] Doğrulama kodu — to=${to} code=${code}`);
    }
    const { subject, html } = verificationEmailTemplate(locale, code);
    await this.send(to, subject, html);
  }

  async sendPasswordResetEmail(to: string, token: string, locale: MailLocale = 'tr') {
    const link = `${this.appUrl}/reset-password?token=${token}`;
    const { subject, html } = passwordResetEmailTemplate(locale, link);
    await this.send(to, subject, html);
  }

  private async send(to: string, subject: string, html: string) {
    if (!this.transporter) {
      this.logger.warn(
        `SMTP yapılandırılmadı (.env), e-posta gönderilmedi. to=${to} subject="${subject}"\n${html}`,
      );
      return;
    }
    await this.transporter.sendMail({ from: this.from, to, subject, html });
  }
}
