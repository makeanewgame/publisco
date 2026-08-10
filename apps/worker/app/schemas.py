from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChapterConfig(BaseModel):
    start_page: int
    title: str


class ConversionOptions(BaseModel):
    """`book_config.json` ile aynı alanları taşır; hepsi opsiyoneldir.

    `/convert` isteğine `options` form alanında JSON string olarak gönderilir.
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
    max_epub_size_mb: float | None = None
    ocr_language: str = "tur+eng"
    page_captions: dict[str, str] = Field(default_factory=dict)

    def to_engine_config(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        if "chapters" in data:
            data["chapters"] = [dict(chapter) for chapter in data["chapters"]]
        return data
