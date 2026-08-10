export type MailLocale = 'tr' | 'en';

export function resolveMailLocale(value?: string | null): MailLocale {
  return value === 'en' ? 'en' : 'tr';
}

const COLORS = {
  primary: '#14b78c',
  primaryDark: '#0e614c',
  mintBg: '#ecfdf7',
  mintBorder: '#a6f4dc',
  pageBg: '#f5f5f5',
  cardBg: '#ffffff',
  text: '#1f2933',
  muted: '#6b7280',
  border: '#e5e7eb',
};

const FONT_STACK =
  "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";

function renderMailLayout(locale: MailLocale, preheader: string, bodyHtml: string) {
  const footer =
    locale === 'en'
      ? 'This is an automated message from publisco — please don\'t reply directly to this email.'
      : 'Bu, publisco tarafından gönderilen otomatik bir e-postadır — lütfen doğrudan yanıtlamayın.';

  return `<!doctype html>
<html lang="${locale}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>publisco</title>
  </head>
  <body style="margin:0;padding:0;background-color:${COLORS.pageBg};font-family:${FONT_STACK};">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">${preheader}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:${COLORS.pageBg};padding:40px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background-color:${COLORS.cardBg};border:1px solid ${COLORS.border};border-radius:12px;overflow:hidden;">
            <tr>
              <td style="padding:28px 32px 0 32px;">
                <span style="font-size:20px;font-weight:700;color:${COLORS.primaryDark};letter-spacing:-0.3px;">publisco</span>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px 8px 32px;color:${COLORS.text};font-size:15px;line-height:1.6;">
                ${bodyHtml}
              </td>
            </tr>
            <tr>
              <td style="padding:24px 32px 28px 32px;border-top:1px solid ${COLORS.border};margin-top:8px;">
                <p style="margin:16px 0 0 0;color:${COLORS.muted};font-size:12px;line-height:1.5;">${footer}</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>`;
}

export function verificationEmailTemplate(locale: MailLocale, code: string) {
  const codeBlock = `<div style="margin:20px 0;padding:18px 16px;background-color:${COLORS.mintBg};border:1px solid ${COLORS.mintBorder};border-radius:10px;text-align:center;">
    <span style="font-family:'SF Mono',Consolas,Menlo,monospace;font-size:32px;font-weight:700;letter-spacing:8px;color:${COLORS.primaryDark};">${code}</span>
  </div>`;

  if (locale === 'en') {
    const body = `<p style="margin:0 0 4px 0;">Enter the code below in the app to verify your account:</p>
      ${codeBlock}
      <p style="margin:0;color:${COLORS.muted};font-size:13px;">This code is valid for 15 minutes. If you didn't request this, you can ignore this email.</p>`;
    return {
      subject: 'Your email verification code',
      html: renderMailLayout(locale, `Your verification code is ${code}`, body),
    };
  }

  const body = `<p style="margin:0 0 4px 0;">Hesabını doğrulamak için aşağıdaki kodu uygulamaya gir:</p>
    ${codeBlock}
    <p style="margin:0;color:${COLORS.muted};font-size:13px;">Bu kod 15 dakika geçerlidir. Bu talebi sen yapmadıysan bu e-postayı yok sayabilirsin.</p>`;
  return {
    subject: 'E-posta doğrulama kodun',
    html: renderMailLayout(locale, `Doğrulama kodun: ${code}`, body),
  };
}

export function passwordResetEmailTemplate(locale: MailLocale, link: string) {
  const button = `<div style="margin:22px 0;text-align:center;">
    <a href="${link}" style="display:inline-block;background-color:${COLORS.primary};color:#ffffff;font-weight:600;font-size:15px;text-decoration:none;padding:12px 28px;border-radius:8px;">${
      locale === 'en' ? 'Reset password' : 'Şifreni sıfırla'
    }</a>
  </div>`;

  if (locale === 'en') {
    const body = `<p style="margin:0 0 4px 0;">We received a request to reset your password. Click the button below to choose a new one:</p>
      ${button}
      <p style="margin:0;color:${COLORS.muted};font-size:13px;">This link is valid for 1 hour. If you didn't request this, you can ignore this email.</p>`;
    return {
      subject: 'Password reset request',
      html: renderMailLayout(locale, 'Reset your publisco password', body),
    };
  }

  const body = `<p style="margin:0 0 4px 0;">Şifreni sıfırlamak için bir talep aldık. Yeni şifreni belirlemek için aşağıdaki butona tıkla:</p>
    ${button}
    <p style="margin:0;color:${COLORS.muted};font-size:13px;">Bu bağlantı 1 saat geçerlidir. Bu talebi sen yapmadıysan bu e-postayı yok sayabilirsin.</p>`;
  return {
    subject: 'Şifre sıfırlama talebi',
    html: renderMailLayout(locale, 'publisco şifreni sıfırla', body),
  };
}
