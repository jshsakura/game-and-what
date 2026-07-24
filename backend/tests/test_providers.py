"""Cover/metadata provider clients: igdb, tgdb, steamgriddb, libretro, artfetch.

Pins the provider-priority/fallback contract these clients promise their callers:
missing API keys report `available: False` (not an exception), HTTP/network
failures degrade to an empty/`None` result instead of raising, and malformed
JSON is treated the same as a miss. httpx is fully replaced by an in-process
fake client (see `_fake_client_cls`) so no test ever touches the network —
this also satisfies the autouse `no_network` fixture, which would otherwise
raise on any real outbound call.
"""
from __future__ import annotations

import time

import httpx
import pytest

from app import config
from app.services import artfetch, igdb, libretro, steamgriddb, tgdb


def _fake_client_cls(handler):
    """Build an httpx.AsyncClient replacement bound to `handler`.

    `handler(method, url, **kwargs)` returns an httpx.Response, or raises to
    simulate a network error. Constructor kwargs (timeout/headers/...) are
    accepted and ignored, like the real client. Every request is recorded on
    the returned class's `.calls` list for assertions on outgoing params/body.
    """
    calls: list[tuple[str, str, dict]] = []

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            return handler("GET", url, **kwargs)

        async def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            return handler("POST", url, **kwargs)

    _Client.calls = calls
    return _Client


def _resp(status=200, json_data=None, text=None):
    if text is not None:
        return httpx.Response(status, text=text)
    return httpx.Response(status, json=json_data)


# ---------------------------------------------------------------------------
# igdb.py
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_igdb_token(monkeypatch):
    """Every test starts with a cold token cache (module-global state)."""
    monkeypatch.setattr(igdb, "_TOKEN", {"value": None, "exp": 0.0})


def _set_igdb_creds(monkeypatch, cid="cid", secret="sec"):
    monkeypatch.setattr(config, "IGDB_CLIENT_ID", cid)
    monkeypatch.setattr(config, "IGDB_CLIENT_SECRET", secret)


def _igdb_client(games_response, monkeypatch, token_status=200):
    """Fake client: OAuth token endpoint + /games endpoint both wired up."""
    def handler(method, url, **kwargs):
        if url.endswith("/oauth2/token"):
            if token_status != 200:
                return _resp(token_status, text="nope")
            return _resp(200, json_data={"access_token": "tok-123", "expires_in": 3600})
        return games_response(method, url, **kwargs) if callable(games_response) else games_response

    cls = _fake_client_cls(handler)
    monkeypatch.setattr(igdb.httpx, "AsyncClient", cls)
    return cls


@pytest.mark.asyncio
async def test_search_covers_empty_query_short_circuits(monkeypatch):
    """Blank query never touches credentials or the network."""
    result = await igdb.search_covers("   ")
    assert result == {"available": True, "results": []}


@pytest.mark.asyncio
async def test_search_covers_unavailable_without_credentials(monkeypatch):
    _set_igdb_creds(monkeypatch, cid="", secret="")
    result = await igdb.search_covers("Mario")
    assert result == {"available": False, "results": []}


@pytest.mark.asyncio
async def test_search_covers_unavailable_when_token_request_fails(monkeypatch):
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=[]), monkeypatch, token_status=401)
    result = await igdb.search_covers("Mario")
    assert result == {"available": False, "results": []}


@pytest.mark.asyncio
async def test_search_covers_reports_network_error(monkeypatch):
    _set_igdb_creds(monkeypatch)

    def handler(method, url, **kwargs):
        if url.endswith("/oauth2/token"):
            return _resp(200, json_data={"access_token": "t", "expires_in": 3600})
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(igdb.httpx, "AsyncClient", _fake_client_cls(handler))
    result = await igdb.search_covers("Mario")
    assert result == {"available": True, "results": [], "error": "IGDB 요청 실패"}


@pytest.mark.asyncio
async def test_search_covers_reports_http_error_status(monkeypatch):
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(500, text="server exploded"), monkeypatch)
    result = await igdb.search_covers("Mario")
    assert result["available"] is True
    assert result["results"] == []
    assert result["error"] == "server exploded"


@pytest.mark.asyncio
async def test_search_covers_filters_games_without_cover_and_fills_year(monkeypatch):
    ts = 1_000_000_000
    games = [
        {"name": "Super Mario Bros.", "first_release_date": ts,
         "cover": {"image_id": "abc123"}},
        {"name": "No Cover Game"},  # missing cover -> filtered out
        {"name": "No Release Date", "cover": {"image_id": "xyz789"}},
    ]
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=games), monkeypatch)

    result = await igdb.search_covers("mario", system="nes")

    assert result["available"] is True
    assert len(result["results"]) == 2
    first = result["results"][0]
    assert first["name"] == "Super Mario Bros."
    assert first["year"] == time.gmtime(ts).tm_year
    assert first["cover_url"] == "https://images.igdb.com/igdb/image/upload/t_cover_big/abc123.jpg"
    assert first["thumb_url"] == "https://images.igdb.com/igdb/image/upload/t_cover_small/abc123.jpg"
    assert result["results"][1]["year"] is None


@pytest.mark.asyncio
async def test_search_covers_applies_platform_filter_for_mapped_system(monkeypatch):
    _set_igdb_creds(monkeypatch)
    cls = _igdb_client(_resp(200, json_data=[]), monkeypatch)

    await igdb.search_covers("kid dracula", system="nes")

    games_call = next(c for c in cls.calls if c[1].endswith("/games"))
    body = games_call[2]["content"]
    assert "platforms = (18,99,51)" in body


@pytest.mark.asyncio
async def test_search_covers_no_platform_filter_for_unmapped_system(monkeypatch):
    _set_igdb_creds(monkeypatch)
    cls = _igdb_client(_resp(200, json_data=[]), monkeypatch)

    await igdb.search_covers("some game", system="unknown-system")

    games_call = next(c for c in cls.calls if c[1].endswith("/games"))
    assert "platforms" not in games_call[2]["content"]


@pytest.mark.asyncio
async def test_resolve_empty_query_returns_none():
    assert await igdb.resolve("") is None


@pytest.mark.asyncio
async def test_resolve_without_credentials_returns_none(monkeypatch):
    _set_igdb_creds(monkeypatch, cid="", secret="")
    assert await igdb.resolve("Mario") is None


@pytest.mark.asyncio
async def test_resolve_network_error_returns_none(monkeypatch):
    _set_igdb_creds(monkeypatch)

    def handler(method, url, **kwargs):
        if url.endswith("/oauth2/token"):
            return _resp(200, json_data={"access_token": "t", "expires_in": 3600})
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(igdb.httpx, "AsyncClient", _fake_client_cls(handler))
    assert await igdb.resolve("Mario") is None


@pytest.mark.asyncio
async def test_resolve_empty_result_list_returns_none(monkeypatch):
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=[]), monkeypatch)
    assert await igdb.resolve("Mario") is None


@pytest.mark.asyncio
async def test_resolve_finds_korean_alternative_name(monkeypatch):
    game = {
        "name": "Super Mario Bros.",
        "cover": {"image_id": "abc123"},
        "alternative_names": [
            {"name": "Super Mario Brothers"},
            {"name": "슈퍼 마리오 브라더스"},
        ],
    }
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=[game]), monkeypatch)

    result = await igdb.resolve("Mario", system="nes")

    assert result["name"] == "Super Mario Bros."
    assert result["korean"] == "슈퍼 마리오 브라더스"
    assert result["cover_url"] == "https://images.igdb.com/igdb/image/upload/t_cover_big/abc123.jpg"


@pytest.mark.asyncio
async def test_resolve_no_korean_name_and_no_cover(monkeypatch):
    game = {"name": "Obscure Game", "alternative_names": [{"name": "Other Name"}]}
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=[game]), monkeypatch)

    result = await igdb.resolve("Obscure Game")

    assert result["korean"] is None
    assert result["cover_url"] is None


@pytest.mark.asyncio
async def test_fetch_rating_empty_query_returns_none():
    assert await igdb.fetch_rating("") is None


@pytest.mark.asyncio
async def test_fetch_rating_without_credentials_returns_none(monkeypatch):
    _set_igdb_creds(monkeypatch, cid="", secret="")
    assert await igdb.fetch_rating("Mario") is None


@pytest.mark.asyncio
async def test_fetch_rating_network_error_returns_none(monkeypatch):
    _set_igdb_creds(monkeypatch)

    def handler(method, url, **kwargs):
        if url.endswith("/oauth2/token"):
            return _resp(200, json_data={"access_token": "t", "expires_in": 3600})
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(igdb.httpx, "AsyncClient", _fake_client_cls(handler))
    assert await igdb.fetch_rating("Mario") is None


@pytest.mark.asyncio
async def test_fetch_rating_non_list_json_returns_none(monkeypatch):
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data={"unexpected": "shape"}), monkeypatch)
    assert await igdb.fetch_rating("Mario") is None


@pytest.mark.asyncio
async def test_fetch_rating_empty_list_returns_none(monkeypatch):
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=[]), monkeypatch)
    assert await igdb.fetch_rating("Mario") is None


@pytest.mark.asyncio
async def test_fetch_rating_low_similarity_returns_none(monkeypatch):
    games = [{"name": "Zzyzx Quantum Beetle Racer", "total_rating": 90}]
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=games), monkeypatch)
    assert await igdb.fetch_rating("Super Mario Bros") is None


@pytest.mark.asyncio
async def test_fetch_rating_confident_match_returns_score(monkeypatch):
    games = [{"name": "Super Mario Bros", "total_rating": 87.6, "total_rating_count": 42}]
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=games), monkeypatch)

    result = await igdb.fetch_rating("Super Mario Bros", system="nes")

    assert result["score"] == 88
    assert result["votes"] == 42
    assert result["name"] == "Super Mario Bros"
    assert result["confidence"] == 1.0


@pytest.mark.asyncio
async def test_fetch_rating_falls_back_through_rating_fields(monkeypatch):
    games = [{"name": "Some Game", "aggregated_rating": 70.0}]
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=games), monkeypatch)

    result = await igdb.fetch_rating("Some Game")

    assert result["score"] == 70
    assert result["votes"] == 0  # total_rating_count absent -> default 0


@pytest.mark.asyncio
async def test_fetch_rating_confident_match_with_no_rating_data(monkeypatch):
    games = [{"name": "Rated Nowhere"}]
    _set_igdb_creds(monkeypatch)
    _igdb_client(_resp(200, json_data=games), monkeypatch)

    result = await igdb.fetch_rating("Rated Nowhere")

    assert result["score"] is None


@pytest.mark.asyncio
async def test_token_is_cached_between_calls(monkeypatch):
    """Second call within the token's lifetime must not re-hit the OAuth endpoint."""
    _set_igdb_creds(monkeypatch)
    cls = _igdb_client(_resp(200, json_data=[]), monkeypatch)

    await igdb.search_covers("first")
    await igdb.search_covers("second")

    token_calls = [c for c in cls.calls if c[1].endswith("/oauth2/token")]
    assert len(token_calls) == 1


# ---------------------------------------------------------------------------
# tgdb.py
# ---------------------------------------------------------------------------

def _set_tgdb_key(monkeypatch, key="tgdb-key"):
    monkeypatch.setattr(config, "TGDB_API_KEY", key)


def test_available_reflects_configured_key(monkeypatch):
    _set_tgdb_key(monkeypatch, key="")
    assert tgdb.available() is False
    _set_tgdb_key(monkeypatch, key="k")
    assert tgdb.available() is True


@pytest.mark.asyncio
async def test_cover_candidates_without_key_returns_empty(monkeypatch):
    _set_tgdb_key(monkeypatch, key="")
    assert await tgdb.cover_candidates("Mario", "nes") == []


@pytest.mark.asyncio
async def test_cover_candidates_blank_name_returns_empty(monkeypatch):
    _set_tgdb_key(monkeypatch)
    assert await tgdb.cover_candidates("   ", "nes") == []


@pytest.mark.asyncio
async def test_cover_url_returns_none_when_no_candidates(monkeypatch):
    _set_tgdb_key(monkeypatch)
    monkeypatch.setattr(tgdb.httpx, "AsyncClient",
                         _fake_client_cls(lambda m, u, **kw: _resp(200, json_data={})))
    assert await tgdb.cover_url("Nothing Matches", "nes") is None


@pytest.mark.asyncio
async def test_search_reports_quota_exceeded_on_429(monkeypatch):
    _set_tgdb_key(monkeypatch)
    monkeypatch.setattr(tgdb.httpx, "AsyncClient",
                         _fake_client_cls(lambda m, u, **kw: _resp(429)))
    result = await tgdb.search("Mario", "nes")
    assert result == {"candidates": [], "quota_exceeded": True}


@pytest.mark.asyncio
async def test_search_network_error_is_not_quota_exceeded(monkeypatch):
    _set_tgdb_key(monkeypatch)

    def handler(method, url, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(tgdb.httpx, "AsyncClient", _fake_client_cls(handler))
    result = await tgdb.search("Mario", "nes")
    assert result == {"candidates": [], "quota_exceeded": False}


@pytest.mark.asyncio
async def test_search_malformed_json_is_treated_as_miss(monkeypatch):
    _set_tgdb_key(monkeypatch)
    monkeypatch.setattr(
        tgdb.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: httpx.Response(200, content=b"not-json{")),
    )
    result = await tgdb.search("Mario", "nes")
    assert result == {"candidates": [], "quota_exceeded": False}


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_games_or_boxart(monkeypatch):
    _set_tgdb_key(monkeypatch)
    monkeypatch.setattr(
        tgdb.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: _resp(200, json_data={
            "data": {"games": []}, "include": {}
        })),
    )
    result = await tgdb.search("Mario", "nes")
    assert result == {"candidates": [], "quota_exceeded": False}


def _tgdb_payload():
    return {
        "data": {"games": [
            {"id": 1, "game_title": "Super Mario Bros."},
            {"id": 2, "game_title": "Duck Hunt"},
        ]},
        "include": {
            "boxart": {
                "base_url": {"original": "https://cdn.example/boxart/"},
                "data": {
                    "1": [
                        {"type": "boxart", "side": "back", "filename": "1-back.jpg"},
                        {"type": "boxart", "side": "front", "filename": "1-front.jpg"},
                        {"type": "boxart", "side": "front", "filename": "1-front2.jpg"},
                    ],
                    "2": [
                        {"type": "boxart", "filename": "2-default-front.jpg"},  # side defaults to front
                    ],
                },
            }
        },
    }


@pytest.mark.asyncio
async def test_cover_candidates_success_picks_first_front_image_per_game(monkeypatch):
    _set_tgdb_key(monkeypatch)
    monkeypatch.setattr(
        tgdb.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: _resp(200, json_data=_tgdb_payload())),
    )

    candidates = await tgdb.cover_candidates("Mario", "nes")

    assert candidates == [
        ("Super Mario Bros.", "https://cdn.example/boxart/1-front.jpg"),
        ("Duck Hunt", "https://cdn.example/boxart/2-default-front.jpg"),
    ]


@pytest.mark.asyncio
async def test_cover_url_returns_first_candidate_url(monkeypatch):
    _set_tgdb_key(monkeypatch)
    monkeypatch.setattr(
        tgdb.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: _resp(200, json_data=_tgdb_payload())),
    )
    url = await tgdb.cover_url("Mario", "nes")
    assert url == "https://cdn.example/boxart/1-front.jpg"


@pytest.mark.asyncio
async def test_request_adds_platform_filter_for_mapped_system(monkeypatch):
    _set_tgdb_key(monkeypatch)
    cls = _fake_client_cls(lambda m, u, **kw: _resp(200, json_data={"data": {"games": []}}))
    monkeypatch.setattr(tgdb.httpx, "AsyncClient", cls)

    await tgdb.cover_candidates("Mario", "nes")
    params = cls.calls[0][2]["params"]
    assert params["filter[platform]"] == 7  # nes -> TGDB platform id 7


@pytest.mark.asyncio
async def test_request_omits_platform_filter_for_unmapped_system(monkeypatch):
    _set_tgdb_key(monkeypatch)
    cls = _fake_client_cls(lambda m, u, **kw: _resp(200, json_data={"data": {"games": []}}))
    monkeypatch.setattr(tgdb.httpx, "AsyncClient", cls)

    await tgdb.cover_candidates("Some Cart", "pico8")
    params = cls.calls[0][2]["params"]
    assert "filter[platform]" not in params


# ---------------------------------------------------------------------------
# steamgriddb.py
# ---------------------------------------------------------------------------

def _set_sgdb_key(monkeypatch, key="sgdb-key"):
    monkeypatch.setattr(config, "STEAMGRIDDB_API_KEY", key)


def test_sgdb_available_reflects_configured_key(monkeypatch):
    _set_sgdb_key(monkeypatch, key="")
    assert steamgriddb.available() is False
    _set_sgdb_key(monkeypatch, key="x")
    assert steamgriddb.available() is True


@pytest.mark.asyncio
async def test_sgdb_search_empty_query_short_circuits(monkeypatch):
    _set_sgdb_key(monkeypatch, key="")
    result = await steamgriddb.search("   ")
    assert result == {"available": False, "results": []}


@pytest.mark.asyncio
async def test_sgdb_search_without_key_is_unavailable(monkeypatch):
    _set_sgdb_key(monkeypatch, key="")
    result = await steamgriddb.search("Mario")
    assert result == {"available": False, "results": []}


@pytest.mark.asyncio
async def test_sgdb_search_reports_bad_key_on_401(monkeypatch):
    _set_sgdb_key(monkeypatch)
    monkeypatch.setattr(steamgriddb.httpx, "AsyncClient",
                         _fake_client_cls(lambda m, u, **kw: _resp(401)))
    result = await steamgriddb.search("Mario")
    assert result["available"] is False
    assert "키가 올바르지" in result["error"]


@pytest.mark.asyncio
async def test_sgdb_search_reports_generic_http_error(monkeypatch):
    _set_sgdb_key(monkeypatch)
    monkeypatch.setattr(steamgriddb.httpx, "AsyncClient",
                         _fake_client_cls(lambda m, u, **kw: _resp(500, text="down")))
    result = await steamgriddb.search("Mario")
    assert result == {"available": True, "results": [], "error": "down"}


@pytest.mark.asyncio
async def test_sgdb_search_no_matches_returns_empty(monkeypatch):
    _set_sgdb_key(monkeypatch)
    monkeypatch.setattr(steamgriddb.httpx, "AsyncClient",
                         _fake_client_cls(lambda m, u, **kw: _resp(200, json_data={"data": []})))
    result = await steamgriddb.search("Mario")
    assert result == {"available": True, "results": []}


@pytest.mark.asyncio
async def test_sgdb_search_reports_network_error(monkeypatch):
    _set_sgdb_key(monkeypatch)

    def handler(method, url, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(steamgriddb.httpx, "AsyncClient", _fake_client_cls(handler))
    result = await steamgriddb.search("Mario")
    assert result == {"available": True, "results": [], "error": "SteamGridDB 요청 실패"}


@pytest.mark.asyncio
async def test_sgdb_search_skips_game_whose_grid_lookup_fails(monkeypatch):
    _set_sgdb_key(monkeypatch)

    def handler(method, url, **kwargs):
        if "autocomplete" in url:
            return _resp(200, json_data={"data": [
                {"id": 1, "name": "Mario"}, {"id": 2, "name": "Mario 2"},
            ]})
        if url.endswith("/grids/game/1"):
            return _resp(500)
        if url.endswith("/grids/game/2"):
            return _resp(200, json_data={"data": [{"url": "https://cdn/grid2.png"}]})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(steamgriddb.httpx, "AsyncClient", _fake_client_cls(handler))
    result = await steamgriddb.search("Mario")
    assert result["available"] is True
    assert result["results"] == [
        {"name": "Mario 2", "year": None, "cover_url": "https://cdn/grid2.png",
         "thumb_url": "https://cdn/grid2.png"}
    ]


@pytest.mark.asyncio
async def test_sgdb_search_ignores_grids_without_url(monkeypatch):
    _set_sgdb_key(monkeypatch)

    def handler(method, url, **kwargs):
        if "autocomplete" in url:
            return _resp(200, json_data={"data": [{"id": 1, "name": "Mario"}]})
        return _resp(200, json_data={"data": [{"thumb": "https://cdn/thumb-only.png"}]})

    monkeypatch.setattr(steamgriddb.httpx, "AsyncClient", _fake_client_cls(handler))
    result = await steamgriddb.search("Mario")
    assert result["results"] == []


@pytest.mark.asyncio
async def test_sgdb_search_uses_thumb_fallback_and_respects_limit(monkeypatch):
    _set_sgdb_key(monkeypatch)

    def handler(method, url, **kwargs):
        if "autocomplete" in url:
            return _resp(200, json_data={"data": [{"id": 1, "name": "Mario"}]})
        return _resp(200, json_data={"data": [
            {"url": "https://cdn/a.png"},
            {"url": "https://cdn/b.png", "thumb": "https://cdn/b-thumb.png"},
        ]})

    monkeypatch.setattr(steamgriddb.httpx, "AsyncClient", _fake_client_cls(handler))
    result = await steamgriddb.search("Mario", limit=1)

    assert result["results"] == [
        {"name": "Mario", "year": None, "cover_url": "https://cdn/a.png",
         "thumb_url": "https://cdn/a.png"}
    ]


@pytest.mark.asyncio
async def test_sgdb_search_skips_autocomplete_entries_without_an_id(monkeypatch):
    _set_sgdb_key(monkeypatch)

    def handler(method, url, **kwargs):
        if "autocomplete" in url:
            return _resp(200, json_data={"data": [{"name": "No Id Game"}]})
        raise AssertionError("grid lookup should not be attempted without an id")

    monkeypatch.setattr(steamgriddb.httpx, "AsyncClient", _fake_client_cls(handler))
    result = await steamgriddb.search("Mario")
    assert result == {"available": True, "results": []}


@pytest.mark.asyncio
async def test_sgdb_search_only_probes_top_games(monkeypatch):
    """_TOP_GAMES=3: a 5-match autocomplete must only trigger 3 grid lookups."""
    _set_sgdb_key(monkeypatch)
    games = [{"id": i, "name": f"Game {i}"} for i in range(1, 6)]

    def handler(method, url, **kwargs):
        if "autocomplete" in url:
            return _resp(200, json_data={"data": games})
        return _resp(200, json_data={"data": []})

    cls = _fake_client_cls(handler)
    monkeypatch.setattr(steamgriddb.httpx, "AsyncClient", cls)

    await steamgriddb.search("Game", limit=100)

    grid_calls = [c for c in cls.calls if "/grids/game/" in c[1]]
    assert len(grid_calls) == 3


# ---------------------------------------------------------------------------
# libretro.py
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_libretro_cache(monkeypatch):
    monkeypatch.setattr(libretro, "_LIST_CACHE", {})


@pytest.mark.asyncio
async def test_search_covers_unmapped_system_is_unavailable():
    result = await libretro.search_covers("Mario", "no-such-system")
    assert result == {"available": False, "results": []}


@pytest.mark.asyncio
async def test_search_covers_unavailable_when_tree_api_errors(monkeypatch):
    monkeypatch.setattr(libretro.httpx, "AsyncClient",
                         _fake_client_cls(lambda m, u, **kw: _resp(500)))
    result = await libretro.search_covers("Mario", "nes")
    assert result == {"available": False, "results": []}


@pytest.mark.asyncio
async def test_search_covers_unavailable_on_network_error(monkeypatch):
    def handler(method, url, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(libretro.httpx, "AsyncClient", _fake_client_cls(handler))
    result = await libretro.search_covers("Mario", "nes")
    assert result == {"available": False, "results": []}


@pytest.mark.asyncio
async def test_search_covers_unavailable_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        libretro.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: httpx.Response(200, content=b"not-json{")),
    )
    result = await libretro.search_covers("Mario", "nes")
    assert result == {"available": False, "results": []}


def _tree_payload():
    return {"tree": [
        {"path": "Named_Boxarts/Super Mario Bros. (USA).png"},
        {"path": "Named_Boxarts/Duck Hunt (USA).png"},
        {"path": "Named_Snaps/Super Mario Bros. (USA).png"},   # wrong dir -> excluded
        {"path": "Named_Boxarts/readme.txt"},                  # not a png -> excluded
    ]}


@pytest.mark.asyncio
async def test_search_covers_success_scores_and_ranks_matches(monkeypatch):
    cls = _fake_client_cls(lambda m, u, **kw: _resp(200, json_data=_tree_payload()))
    monkeypatch.setattr(libretro.httpx, "AsyncClient", cls)

    result = await libretro.search_covers("super mario bros", "nes")

    assert result["available"] is True
    assert result["results"][0]["name"] == "Super Mario Bros. (USA)"
    assert result["results"][0]["cover_url"] == (
        "https://raw.githubusercontent.com/libretro-thumbnails/"
        "Nintendo_-_Nintendo_Entertainment_System/master/Named_Boxarts/"
        "Super%20Mario%20Bros.%20%28USA%29.png"
    )
    assert all("Duck Hunt" not in r["name"] for r in result["results"][:1])


@pytest.mark.asyncio
async def test_search_covers_no_match_returns_empty_results(monkeypatch):
    cls = _fake_client_cls(lambda m, u, **kw: _resp(200, json_data=_tree_payload()))
    monkeypatch.setattr(libretro.httpx, "AsyncClient", cls)

    result = await libretro.search_covers("completely unrelated query text", "nes")

    assert result == {"available": True, "results": []}


@pytest.mark.asyncio
async def test_boxart_list_is_cached_across_calls(monkeypatch):
    cls = _fake_client_cls(lambda m, u, **kw: _resp(200, json_data=_tree_payload()))
    monkeypatch.setattr(libretro.httpx, "AsyncClient", cls)

    await libretro.search_covers("mario", "nes")
    await libretro.search_covers("duck", "nes")

    assert len(cls.calls) == 1  # second call served from _LIST_CACHE


def test_score_exact_prefix_substring_and_token_overlap():
    assert libretro._score("mario", {"mario"}, "mario") == 100
    assert libretro._score("mario", {"mario"}, "mario bros") == 80
    assert libretro._score("mario bros", {"mario", "bros"}, "super mario bros usa") == 60
    assert libretro._score("mario kart", {"mario", "kart"}, "kart racer mario") > 0
    assert libretro._score("zzz", {"zzz"}, "totally unrelated") == -1
    assert libretro._score("mario", {"mario"}, "") == -1


def test_norm_strips_extension_and_tags():
    assert libretro._norm("Super Mario Bros. (USA) [!].png") == "super mario bros"


# ---------------------------------------------------------------------------
# artfetch.py
# ---------------------------------------------------------------------------

# fetch_image now resolves the URL's host over DNS to block SSRF (see the
# _is_safe_target tests below, which exercise that check for real). The fake
# "cdn.example" hostnames used here don't resolve to anything, so these
# response-handling tests bypass the check — it's not what they're testing.
def _allow_any_target(monkeypatch):
    monkeypatch.setattr(artfetch, "_is_safe_target", lambda url: True)


@pytest.mark.asyncio
async def test_fetch_image_success_returns_bytes(monkeypatch):
    _allow_any_target(monkeypatch)
    monkeypatch.setattr(
        artfetch.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: httpx.Response(200, content=b"\x89PNGdata")),
    )
    data = await artfetch.fetch_image("https://cdn.example/cover.png")
    assert data == b"\x89PNGdata"


@pytest.mark.asyncio
async def test_fetch_image_non_200_returns_none(monkeypatch):
    _allow_any_target(monkeypatch)
    monkeypatch.setattr(artfetch.httpx, "AsyncClient",
                         _fake_client_cls(lambda m, u, **kw: httpx.Response(404)))
    assert await artfetch.fetch_image("https://cdn.example/missing.png") is None


@pytest.mark.asyncio
async def test_fetch_image_empty_body_returns_none(monkeypatch):
    _allow_any_target(monkeypatch)
    monkeypatch.setattr(
        artfetch.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: httpx.Response(200, content=b"")),
    )
    assert await artfetch.fetch_image("https://cdn.example/empty.png") is None


@pytest.mark.asyncio
async def test_fetch_image_oversized_body_returns_none(monkeypatch):
    _allow_any_target(monkeypatch)
    monkeypatch.setattr(artfetch, "_MAX_ART_BYTES", 10)
    monkeypatch.setattr(
        artfetch.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: httpx.Response(200, content=b"x" * 11)),
    )
    assert await artfetch.fetch_image("https://cdn.example/huge.png") is None


@pytest.mark.asyncio
async def test_fetch_image_network_error_returns_none(monkeypatch):
    _allow_any_target(monkeypatch)

    def handler(method, url, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(artfetch.httpx, "AsyncClient", _fake_client_cls(handler))
    assert await artfetch.fetch_image("https://cdn.example/cover.png") is None


@pytest.mark.asyncio
async def test_fetch_image_os_error_returns_none(monkeypatch):
    _allow_any_target(monkeypatch)

    def handler(method, url, **kwargs):
        raise OSError("disk on fire")

    monkeypatch.setattr(artfetch.httpx, "AsyncClient", _fake_client_cls(handler))
    assert await artfetch.fetch_image("https://cdn.example/cover.png") is None


# ── SSRF guard (_is_safe_target) — these exercise the real check, so they
#    use literal IP addresses / loopback, which getaddrinfo resolves locally
#    without any real DNS/network round-trip. ───────────────────────────────

@pytest.mark.asyncio
async def test_fetch_image_rejects_loopback_target(monkeypatch):
    calls = []

    def handler(method, url, **kw):
        calls.append(url)
        return httpx.Response(200, content=b"\x89PNGdata")

    monkeypatch.setattr(artfetch.httpx, "AsyncClient", _fake_client_cls(handler))
    assert await artfetch.fetch_image("http://127.0.0.1:6379/") is None
    assert calls == []


@pytest.mark.asyncio
async def test_fetch_image_rejects_link_local_metadata_target(monkeypatch):
    monkeypatch.setattr(
        artfetch.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: httpx.Response(200, content=b"\x89PNGdata")),
    )
    assert await artfetch.fetch_image("http://169.254.169.254/latest/meta-data/") is None


@pytest.mark.asyncio
async def test_fetch_image_rejects_non_http_scheme(monkeypatch):
    monkeypatch.setattr(
        artfetch.httpx, "AsyncClient",
        _fake_client_cls(lambda m, u, **kw: httpx.Response(200, content=b"\x89PNGdata")),
    )
    assert await artfetch.fetch_image("file:///etc/passwd") is None


@pytest.mark.asyncio
async def test_fetch_image_rejects_redirect_to_private_target(monkeypatch):
    """A public-looking URL that 302s to an internal host must not be fetched —
    the redirect target is re-validated, not followed blindly."""
    monkeypatch.setattr(artfetch, "_is_safe_target",
                         lambda url: "example.com" in url)

    def handler(method, url, **kw):
        if "example.com" in url:
            return httpx.Response(302, headers={"location": "http://10.0.0.5/internal"})
        return httpx.Response(200, content=b"\x89PNGdata")

    monkeypatch.setattr(artfetch.httpx, "AsyncClient", _fake_client_cls(handler))
    assert await artfetch.fetch_image("https://example.com/redirect") is None
