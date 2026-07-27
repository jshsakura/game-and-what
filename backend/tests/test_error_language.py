# -*- coding: utf-8 -*-
"""Every HTTPException detail must be in the source language.

English is this project's source language: in-code strings ARE the i18n keys (see
frontend/src/i18n.jsx). An API error written in Korean is therefore untranslatable —
it never matches a key, so it reaches the toast verbatim and a German user is shown
한글. That is what this used to do, in 68 places.

This test is the reason it will not come back. Adding one Korean `detail=` anywhere in
app/ fails the suite, and the fix is to write it in English and put the Korean in
frontend/src/locales/ko.js like every other string.
"""
import ast
import pathlib
import re

HANGUL = re.compile(r"[가-힣]")
APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def _detail_sources() -> list[tuple[str, int, str]]:
    """Every `detail=` expression in an HTTPException, as written in the source."""
    out = []
    for path in sorted(APP.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "HTTPException"):
                continue
            for kw in node.keywords:
                if kw.arg == "detail":
                    text = ast.get_source_segment(src, kw.value) or ""
                    out.append((str(path.relative_to(APP.parent)), node.lineno, text))
    return out


def test_no_hangul_in_any_error_detail():
    offenders = [f"{f}:{n}  {t}" for f, n, t in _detail_sources() if HANGUL.search(t)]
    assert not offenders, (
        "HTTPException detail must be English (the i18n source language) — put the "
        "Korean in frontend/src/locales/ko.js instead:\n  " + "\n  ".join(offenders)
    )


def test_there_are_details_to_check():
    """Guards the guard: if the AST walk ever stopped matching (a rename, an import
    style change), the test above would pass on an empty list and prove nothing."""
    assert len(_detail_sources()) > 100


# NOT tested here: that an interpolated detail puts its value after ": " so the stem
# can be translated (see translateMessage in toast.jsx). The messages converted from
# Korean all follow it, but eight older English ones interpolate mid-sentence — mostly
# chunked-upload protocol errors a user never reads. Enforcing the convention would
# mean rewriting those for no one's benefit, so it stays a convention for new messages
# rather than a rule with eight exemptions.
