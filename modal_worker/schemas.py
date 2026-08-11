from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChapterConfig(BaseModel):
    start_page: int
    title: str


class ConversionOptions(BaseModel):
    """`book_config.json` ile aynı alanları taşır (hedef boyuta sıkıştırma
    hariç — `max_epub_size_mb` v1 kapsamı dışında, bkz. NOTES.md); hepsi
    opsiyoneldir. Vercel API'sinden `/convert` isteğine JSON body olarak
    gönderilir.
    """

    title: str | None = None
    author: str | None = None
    language: str = "tr"
    start_page: int | None = None
    end_page: int | None = None
    skip_pages: list[int] = Field(default_factory=list)
    diagram_pages: list[int] = Field(default_factory=list)
    chapters: list[ChapterConfig] | None = None
    cover_page: int | None = None
    visual_mode: bool = False
    auto_visual_mode: bool = False
    image_profile: str = "balanced"
    image_dpi: int | None = None
    image_quality: int | None = None
    ocr_language: str = "tur+eng"
    page_captions: dict[str, str] = Field(default_factory=dict)

    def to_engine_config(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        if "chapters" in data:
            data["chapters"] = [dict(chapter) for chapter in data["chapters"]]
        return data


class ConvertRequest(BaseModel):
    """Vercel API'sinin Modal'ın `/convert` web_endpoint'ine POST ettiği gövde."""

    job_id: str
    pdf_url: str
    title: str | None = None
    author: str | None = None
    language: str = "tr"
    options: ConversionOptions = Field(default_factory=ConversionOptions)
    force_ocr: bool = False


class AnalyzeRequest(BaseModel):
    """Vercel API'sinin Modal'ın `/analyze` web_endpoint'ine POST ettiği gövde.

    `/convert` ile aynı desen: dosya bayt olarak taşınmaz, sadece Blob URL'i —
    PDF'in kendisi hâlâ Vercel'in ~4.5MB inbound body limitine tabi olan
    Vercel Function'a hiç girmemesi gerekiyor (client doğrudan Blob'a yükler,
    bkz. ConvertService.createAnalyzeUploadToken).
    """

    pdf_url: str
