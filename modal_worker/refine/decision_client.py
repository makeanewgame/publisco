"""Vercel AI Gateway üzerindeki karar ("evaluation") modellerine tipli istemci.

Bu modeller metin üretmez: bir `state` ve onun hakkında sorular alır, her soru
için 0-1 arası "evet" olasılığı döner. Gateway'deki karar modelleri (ör.
`microsoft/microsoft-decision-1`, `typesafe-ai/jev`, `openai/gpt-6-luna-decisions`)
aynı uç noktadan, yalnızca model adı değiştirilerek çağrılır.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests
from pydantic import BaseModel, ValidationError

from .paragraph_flow import JoinCandidate

logger = logging.getLogger("modal_worker.refine")

GATEWAY_URL = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
# Pilotta (bkz. ROADMAP.md) kodun önerdiği 124 doğru birleştirmenin hiçbirini reddetmeyen tek model.
DEFAULT_MODEL = "microsoft/microsoft-decision-1"
REQUEST_TIMEOUT_SECONDS = 30
MAX_WORKERS = 4  # uç nokta hız sınırı uyguluyor
# Olasılık bunun altındaysa model "hayır" demiş sayılır ve birleştirme veto edilir.
VETO_BELOW = 0.5


class NoulQuestion(BaseModel):
    type: Literal["noul"] = "noul"
    instructions: str


class DecisionRequest(BaseModel):
    model: str
    state: dict[str, str]
    questions: dict[str, NoulQuestion]


class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float


class Usage(BaseModel):
    input_tokens: int = 0


class DecisionResponse(BaseModel):
    answers: dict[str, NoulAnswer]
    usage: Usage = Usage()


SAME_WORD = NoulQuestion(
    instructions=(
        "prev_end is the end of one text block and ends with a hyphen. next_start is the "
        "beginning of the following block. Is the hyphen only a line-break hyphen, i.e. the "
        "fragment before it and the first word of next_start are two halves of ONE word that "
        "should be written together without the hyphen?"
    )
)
SAME_PARAGRAPH = NoulQuestion(
    instructions=(
        "prev_end is the end of one text block and next_start is the beginning of the following "
        "block, extracted from a book PDF. Does next_start continue the same sentence or "
        "paragraph as prev_end (the two were split only by a line or page break), rather than "
        "starting a new paragraph, heading or caption?"
    )
)


@dataclass
class DecisionUsage:
    input_tokens: int = 0
    error_count: int = 0
    cache_hits: int = 0


class DecisionClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, cache_dir: Path | None = None):
        self.api_key = api_key
        self.model = model
        self.cache_dir = cache_dir  # yalnızca eval: aynı soru ikinci kez ücretlendirilmez, koşular tekrarlanabilir olur

    @classmethod
    def from_env(cls, cache_dir: Path | None = None) -> "DecisionClient | None":
        api_key = os.environ.get("AI_GATEWAY_API_KEY")
        if not api_key:
            return None
        return cls(api_key, os.environ.get("REFINE_MODEL", DEFAULT_MODEL), cache_dir)

    def _cache_path(self, request: DecisionRequest) -> Path | None:
        if self.cache_dir is None:
            return None
        key = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        return self.cache_dir / key[:2] / f"{key}.json"

    def ask(self, state: dict[str, str], questions: dict[str, NoulQuestion]) -> tuple[DecisionResponse | None, bool]:
        """(yanıt, önbellekten-mi) döner; çağrı ya da doğrulama başarısızsa yanıt None'dır."""
        request = DecisionRequest(model=self.model, state=state, questions=questions)
        cache_path = self._cache_path(request)
        if cache_path is not None and cache_path.exists():
            try:
                return DecisionResponse.model_validate_json(cache_path.read_text(encoding="utf-8")), True
            except ValidationError:
                pass

        try:
            http_response = requests.post(
                GATEWAY_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=request.model_dump(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            http_response.raise_for_status()
            response = DecisionResponse.model_validate(http_response.json())
        except (requests.RequestException, ValidationError, ValueError) as exc:
            logger.warning("Karar modeli çağrısı başarısız (%s): %s", self.model, exc)
            return None, False
        if set(response.answers) != set(questions):
            logger.warning("Karar modeli eksik/fazla yanıt döndü (%s).", self.model)
            return None, False

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(response.model_dump_json(), encoding="utf-8")
        return response, False


def veto_join_candidates(client: DecisionClient, candidates: list[JoinCandidate]) -> tuple[set[int], DecisionUsage]:
    """Her adayı modele sorar; modelin "hayır" dediklerinin id'lerini döner.
    Yanıt alınamayan aday veto EDİLMEZ (kural geçerli kalır)."""
    usage = DecisionUsage()

    def ask(candidate: JoinCandidate) -> tuple[DecisionResponse | None, bool]:
        questions = {"same_paragraph": SAME_PARAGRAPH}
        if candidate.kind == "hyphen":
            questions["same_word"] = SAME_WORD
        return client.ask({"prev_end": candidate.prev_end, "next_start": candidate.next_start}, questions)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(ask, candidates))

    vetoed: set[int] = set()
    for candidate, (response, from_cache) in zip(candidates, results):
        if response is None:
            usage.error_count += 1
            continue
        if from_cache:
            usage.cache_hits += 1
        else:
            usage.input_tokens += response.usage.input_tokens
        if any(answer.noul < VETO_BELOW for answer in response.answers.values()):
            vetoed.add(candidate.id)
    return vetoed, usage
