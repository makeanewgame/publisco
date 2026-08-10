import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuthProvider, MembershipTier } from '../generated/prisma/client';
import { CONVERTER_QUOTA_BYTES, STORAGE_QUOTA_BYTES } from '../quota/quota.constants';

@Injectable()
export class UsersService {
  constructor(private readonly prisma: PrismaService) {}

  findByEmail(email: string) {
    return this.prisma.user.findUnique({ where: { email } });
  }

  findById(id: string) {
    return this.prisma.user.findUnique({ where: { id } });
  }

  findByGoogleId(googleId: string) {
    return this.prisma.user.findUnique({ where: { googleId } });
  }

  createLocalUser(data: { email: string; passwordHash: string; name?: string; locale?: string }) {
    return this.prisma.user.create({
      data: {
        email: data.email,
        passwordHash: data.passwordHash,
        name: data.name,
        provider: AuthProvider.LOCAL,
        locale: data.locale,
        quota: { create: defaultQuotaData(MembershipTier.FREE) },
      },
    });
  }

  createGoogleUser(data: {
    email: string;
    googleId: string;
    name?: string;
    avatarUrl?: string;
    locale?: string;
  }) {
    return this.prisma.user.create({
      data: {
        email: data.email,
        googleId: data.googleId,
        name: data.name,
        avatarUrl: data.avatarUrl,
        provider: AuthProvider.GOOGLE,
        emailVerified: true,
        locale: data.locale,
        quota: { create: defaultQuotaData(MembershipTier.FREE) },
      },
    });
  }

  linkGoogleAccount(userId: string, googleId: string, avatarUrl?: string) {
    return this.prisma.user.update({
      where: { id: userId },
      data: {
        googleId,
        avatarUrl: avatarUrl ?? undefined,
        emailVerified: true,
      },
    });
  }

  updatePassword(userId: string, passwordHash: string) {
    return this.prisma.user.update({
      where: { id: userId },
      data: { passwordHash },
    });
  }

  markEmailVerified(userId: string) {
    return this.prisma.user.update({
      where: { id: userId },
      data: { emailVerified: true },
    });
  }
}

export function defaultQuotaData(tier: MembershipTier) {
  return {
    storageQuotaBytes: BigInt(STORAGE_QUOTA_BYTES[tier]),
    converterQuotaBytes:
      CONVERTER_QUOTA_BYTES[tier] === null ? null : BigInt(CONVERTER_QUOTA_BYTES[tier] as number),
  };
}
