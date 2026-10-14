"""`refine/` katmanı: paragraf birleştirme adayları, uygulama ve model vetosu."""

from __future__ import annotations

from dataclasses import dataclass

from converter import ChapterPlan, PageResult, PlanResult
from refine import refine_page_results
from refine.decision_client import DecisionResponse, veto_join_candidates
from refine.paragraph_flow import apply_joins, classify_boundary, find_join_candidates

LONG = "Yolun sonunda uzun zamandır görmediği eski bir arkadaşıyla karşılaştı"


def _plan(mode: str, chapter_starts: tuple[int, ...] = (1,)) -> PlanResult:
    chapters = [ChapterPlan(start_page=s, end_page=s, title=f"B{s}") for s in chapter_starts]
    return PlanResult(total_pages=9, resolved_config={"refine_mode": mode}, chapters=chapters, chunks=[(1, 9)])


def test_classify_boundary():
    assert classify_boundary("şehrin en eski ma-", "hallesine doğru yürüdü.") == "hyphen"
    assert classify_boundary("şehrin en eski ma­", "hallesine doğru yürüdü.") == "hyphen"
    assert classify_boundary(LONG + " ve", "onunla konuştu.") == "split"
    assert classify_boundary(LONG + ".", "onunla konuştu.") is None  # cümle bitmiş
    assert classify_boundary(LONG + " ve", "Onunla konuştu.") is None  # büyük harfle başlıyor
    assert classify_boundary("Giriş", "ertesi gün yola çıktı.") is None  # kısa blok: başlık/etiket


def test_joins_within_page_and_across_pages_with_chaining():
    pages = [
        PageResult(page_num=1, html=f"<p>Önceki cümle bitti.</p>\n<p>{LONG} ve</p>\n<p>onunla bir süre ko-</p>"),
        PageResult(page_num=2, html='<img src="images/p2.png" alt="x" />\n<p>nuştu &amp; ayrıldı.</p>\n<p>Yeni paragraf.</p>'),
    ]
    candidates = find_join_candidates(pages)
    assert [(c.kind, c.prev_page, c.next_page) for c in candidates] == [("split", 1, 1), ("hyphen", 1, 2)]

    assert apply_joins(pages, candidates) == 2
    assert pages[0].html == f"<p>Önceki cümle bitti.</p>\n<p>{LONG} ve onunla bir süre konuştu &amp; ayrıldı.</p>"
    assert pages[1].html == '<img src="images/p2.png" alt="x" />\n<p>Yeni paragraf.</p>'


def test_headings_inline_images_and_chapter_starts_block_joins():
    pages = [
        PageResult(page_num=1, html=f"<p>{LONG} ve</p>\n<h2>Başlık</h2>\n<p>onunla konuştu.</p>"),
        PageResult(page_num=2, html=f'<p>{LONG} ve</p>\n<img src="a.png" alt="x" />\n<p>onunla konuştu.</p>\n<p>{LONG} ve</p>'),
        PageResult(page_num=3, html="<p>onunla konuştu.</p>"),
    ]
    assert find_join_candidates(pages, chapter_start_pages={3}) == []
    assert len(find_join_candidates(pages)) == 1  # bölüm sınırı olmasa 2->3 birleşirdi


def test_refine_modes_off_and_rules():
    def pages():
        return [PageResult(page_num=1, html=f"<p>{LONG} ve</p>\n<p>onunla konuştu.</p>")]

    off = pages()
    assert refine_page_results(_plan("off"), off).candidate_count == 0
    assert off[0].html == pages()[0].html

    ruled = pages()
    report = refine_page_results(_plan("rules"), ruled)
    assert (report.candidate_count, report.joined_count, report.vetoed_count) == (1, 1, 0)
    assert ruled[0].html == f"<p>{LONG} ve onunla konuştu.</p>"


@dataclass
class _FakeClient:
    """`next_start`'ın ilk kelimesine göre olasılık döner; None = çağrı hatası."""

    probabilities: dict[str, float | None]
    model: str = "fake"

    def ask(self, state, questions):
        probability = self.probabilities[state["next_start"].split()[0]]
        if probability is None:
            return None, False
        answers = {name: {"type": "noul", "noul": probability} for name in questions}
        return DecisionResponse.model_validate({"answers": answers, "usage": {"input_tokens": 10}}), False


def test_model_vetoes_low_probability_and_keeps_rule_on_error():
    html = "\n".join(
        [f"<p>{LONG} ve</p>", "<p>birinci devam.</p>", f"<p>{LONG} ve</p>", "<p>ikinci devam.</p>", f"<p>{LONG} ve</p>", "<p>üçüncü devam.</p>"]
    )
    pages = [PageResult(page_num=1, html=html)]
    candidates = find_join_candidates(pages)
    assert len(candidates) == 3

    client = _FakeClient({"birinci": 0.9, "ikinci": 0.1, "üçüncü": None})
    vetoed, usage = veto_join_candidates(client, candidates)
    assert vetoed == {1}
    assert (usage.error_count, usage.input_tokens) == (1, 20)

    report = refine_page_results(_plan("model"), pages, decision_client=_FakeClient({"birinci": 0.9, "ikinci": 0.1, "üçüncü": None}))
    assert (report.joined_count, report.vetoed_count, report.model_error_count) == (2, 1, 1)
    assert pages[0].html.split("\n") == [
        f"<p>{LONG} ve birinci devam.</p>",
        f"<p>{LONG} ve</p>",
        "<p>ikinci devam.</p>",
        f"<p>{LONG} ve üçüncü devam.</p>",
    ]


def test_figure_at_page_end_does_not_block_cross_page_join():
    pages = [
        PageResult(page_num=1, html=f'<p>{LONG} ve</p>\n<img src="fig.png" alt="x" />'),
        PageResult(page_num=2, html="<p>onunla konuştu.</p>"),
    ]
    candidates = find_join_candidates(pages)
    assert len(candidates) == 1
    apply_joins(pages, candidates)
    assert pages[0].html == f'<p>{LONG} ve onunla konuştu.</p>\n<img src="fig.png" alt="x" />'
    assert pages[1].html == ""


def test_strip_duplicate_chapter_titles():
    from refine.paragraph_flow import strip_duplicate_chapter_titles

    pages = [
        PageResult(page_num=1, html="<p>Bölüm 1  Bilimsel Yazım Nedir? Epigraf cümlesi.</p>\n<p>Gövde.</p>"),
        PageResult(page_num=2, html='<img src="a.png" alt="x" />\n<h2>2. BÖLÜM</h2>\n<p>Gövde.</p>'),
        PageResult(page_num=3, html="<p>Bambaşka bir cümleyle başlıyor.</p>"),
        PageResult(page_num=4, html="<p>Ekler listesi aşağıdadır.</p>"),
    ]
    chapters = [
        ChapterPlan(start_page=1, end_page=1, title="Bölüm 1 Bilimsel Yazım Nedir?"),
        ChapterPlan(start_page=2, end_page=2, title="2. BÖLÜM"),
        ChapterPlan(start_page=3, end_page=3, title="Üçüncü Bölüm"),
        ChapterPlan(start_page=4, end_page=4, title="Ek"),
    ]

    assert strip_duplicate_chapter_titles(pages, chapters) == 2
    assert pages[0].html == "<p>Epigraf cümlesi.</p>\n<p>Gövde.</p>"
    assert pages[1].html == '<img src="a.png" alt="x" />\n<p>Gövde.</p>'
    assert pages[2].html == "<p>Bambaşka bir cümleyle başlıyor.</p>"
    assert pages[3].html == "<p>Ekler listesi aşağıdadır.</p>"  # "Ek" kelimenin öneki, başlık tekrarı değil


def test_demote_false_headings_only_below_threshold():
    from refine.headings import demote_false_headings

    class Client:
        model = "fake"

        def ask(self, state, questions):
            p = {"Plato": 0.02, "AÇIKLIK GEREKSİNİMİ": 0.9, "HAYDEN": 0.3}[state["line"]]
            if state["line"] == "Plato":
                assert state["previous_text"].endswith("güzelliği.") and state["next_text"] == "AÇIKLIK GEREKSİNİMİ"
            return DecisionResponse.model_validate({"answers": {"is_heading": {"type": "noul", "noul": p}}}), False

    pages = [
        PageResult(page_num=1, html="<p>Basitliğin güzelliği.</p>\n<h2>Plato</h2>\n<h2>AÇIKLIK GEREKSİNİMİ</h2>"),
        PageResult(page_num=2, html="<h2>HAYDEN</h2>\n<p>Gövde.</p>\n<h2>Sayfa 2</h2>"),
    ]
    usage = demote_false_headings(pages, Client())

    assert (usage.candidate_count, usage.demoted_count) == (3, 1)  # "Sayfa 2" sorulmaz
    assert pages[0].html == "<p>Basitliğin güzelliği.</p>\n<p>Plato</p>\n<h2>AÇIKLIK GEREKSİNİMİ</h2>"
    assert pages[1].html == "<h2>HAYDEN</h2>\n<p>Gövde.</p>\n<h2>Sayfa 2</h2>"
