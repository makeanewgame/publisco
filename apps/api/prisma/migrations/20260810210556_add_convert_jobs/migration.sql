-- CreateTable
CREATE TABLE "convert_jobs" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "fileSizeBytes" INTEGER NOT NULL,
    "released" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "convert_jobs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "convert_jobs_userId_idx" ON "convert_jobs"("userId");

-- AddForeignKey
ALTER TABLE "convert_jobs" ADD CONSTRAINT "convert_jobs_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
