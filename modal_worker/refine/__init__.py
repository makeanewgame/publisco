"""Map ile reduce arasında çalışan düzeltme katmanı (bkz. ROADMAP.md "Yeni yön").

Kod adayı bulur ve kuralı uygular; `mode="model"` ise bir karar modeli kuralın
yanlış olduğu adayları veto eder. Metni her zaman kod yazar -- model yalnızca
0-1 arası olasılık döner, bu yüzden model katmanı içerik uyduramaz.

Modlar (`config["refine_mode"]`, varsayılan "off"):
  - "off":   hiçbir şey yapmaz (pipeline'ın eski davranışı).
  - "rules": kuralın önerdiği tüm birleştirmeler uygulanır.
  - "model": kuralın önerdikleri karar modeline sorulur; model "hayır" derse
             birleştirme yapılmaz. Model çağrısı başarısız olursa kural geçerlidir.
"""

from __future__ import annotations

import logging
from typing import Any

from .paragraph_flow import RefineReport, apply_joins, find_join_candidates

logger = logging.getLogger("modal_worker.refine")

REFINE_MODES = ("off", "rules", "model")


def refine_page_results(plan: Any, page_results: list[Any], decision_client: Any | None = None) -> RefineReport:
    """`page_results`'ı YERİNDE düzeltir (yalnızca `.html`), ne yaptığını raporlar.

    `plan`: `converter.PlanResult` (mod `resolved_config`'ten, bölüm başlangıç
    sayfaları `chapters`'tan okunur). `decision_client` verilmezse ve mod
    "model" ise ortam değişkenlerinden kurulur."""
    mode = plan.resolved_config.get("refine_mode", "off")
    if mode not in REFINE_MODES:
        logger.warning("Bilinmeyen refine_mode %r, 'off' sayıldı.", mode)
        mode = "off"
    report = RefineReport(mode=mode)
    if mode == "off":
        return report

    chapter_start_pages = {chapter.start_page for chapter in plan.chapters}
    candidates = find_join_candidates(page_results, chapter_start_pages)
    report.candidate_count = len(candidates)
    if not candidates:
        return report

    vetoed_ids: set[int] = set()
    if mode == "model":
        from .decision_client import DecisionClient, veto_join_candidates

        client = decision_client or DecisionClient.from_env()
        if client is None:
            logger.warning("refine_mode=model ama AI_GATEWAY_API_KEY yok; yalnızca kurallar uygulanıyor.")
        else:
            vetoed_ids, usage = veto_join_candidates(client, candidates)
            report.model = client.model
            report.model_error_count = usage.error_count
            report.input_tokens = usage.input_tokens
            report.cache_hits = usage.cache_hits

    report.vetoed_count = len(vetoed_ids)
    report.joined_count = apply_joins(page_results, candidates, vetoed_ids)
    logger.info(
        "refine(%s): %d aday, %d birleştirildi, %d veto, %d model hatası",
        mode, report.candidate_count, report.joined_count, report.vetoed_count, report.model_error_count,
    )
    return report
