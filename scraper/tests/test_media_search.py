from media_search import aggregate_observations, extract_observations, merge_archive


def candidate(country="CZ", source_type="media_or_other_public_source"):
    return {
        "country": country,
        "url": "https://example.com/card-fees",
        "title": "Card fee report",
        "source_name": "Example",
        "source_type": source_type,
        "published_date": "2026-06-01",
        "language": "cs",
        "search_engine": "brave",
    }


def test_multilingual_scheme_processing_and_fixed_fee_extraction():
    text = (
        "Poplatek karetního schématu Visa činí 0,08 % pro spotřebitelské karty. "
        "Poplatek za zpracování karetní transakce je 0,02 EUR za transakci."
    )
    items = extract_observations(candidate(), text, from_full_page=False)
    assert {(i["fee_type"], i["value_kind"]) for i in items} == {
        ("scheme_fee", "percent"),
        ("processing_fee", "fixed"),
    }
    scheme = next(i for i in items if i["fee_type"] == "scheme_fee")
    assert scheme["network"] == "visa"
    assert scheme["card_segment"] == "consumer"
    assert scheme["value_low"] == 0.08


def test_merchant_service_charge_range_extraction():
    text = "Obchodníci platí poplatek za přijímání karet v rozmezí 0,7 až 1,2 %."
    items = extract_observations(candidate(), text, from_full_page=False)
    assert len(items) == 1
    item = items[0]
    assert item["fee_type"] == "merchant_service_charge"
    assert item["value_low"] == 0.7
    assert item["value_high"] == 1.2


def test_basis_points_are_normalised_to_percentage_points():
    text = "The Mastercard commercial card scheme fee is 18 basis points."
    items = extract_observations(candidate(country="DE"), text, from_full_page=False)
    assert len(items) == 1
    assert items[0]["value_low"] == 0.18
    assert items[0]["network"] == "mastercard"
    assert items[0]["card_segment"] == "commercial"


def test_archive_merge_is_deduplicated_and_tracks_first_last_seen():
    current_item = extract_observations(
        candidate(), "Visa scheme fee is 0.08 percent for consumer cards.", from_full_page=False
    )[0]
    current_item["discovered_at"] = "2026-07-01T00:00:00+00:00"
    previous = {"items": [{**current_item, "discovered_at": "2026-06-01T00:00:00+00:00"}]}
    current = {"generated_at": "2026-07-01T00:00:00+00:00", "items": [current_item], "search_status": {}}
    merged = merge_archive(previous, current)
    assert len(merged["items"]) == 1
    assert merged["items"][0]["first_seen_at"] == "2026-06-01T00:00:00+00:00"
    assert merged["items"][0]["last_seen_at"] == "2026-07-01T00:00:00+00:00"


def test_public_summary_keeps_networks_and_fee_types_separate():
    visa = extract_observations(candidate(), "Visa scheme fee is 0.08 percent for consumer cards.", from_full_page=False)[0]
    mc = extract_observations(candidate(), "Mastercard scheme fee is 0.10 percent for consumer cards.", from_full_page=False)[0]
    summary = aggregate_observations([visa, mc])
    assert len(summary) == 2
    assert {row["network"] for row in summary} == {"visa", "mastercard"}


def test_transaction_amount_is_not_mistaken_for_fixed_fee():
    text = "The scheme fee is 0.08% on a transaction of 50 EUR."
    items = extract_observations(candidate(), text, from_full_page=False)
    assert any(i["fee_type"] == "scheme_fee" and i["value_kind"] == "percent" for i in items)
    assert not any(i["value_kind"] == "fixed" and i["value_low"] == 50 for i in items)


def test_brave_client_normalises_web_results(monkeypatch):
    import media_search
    from sources import COUNTRY_BY_ISO2

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"web": {"results": [{
                "title": "<b>Visa fee</b>",
                "url": "https://example.com/fee/",
                "description": "Visa scheme fee is 0.08%.",
                "extra_snippets": ["Consumer cards."],
            }]}}

    monkeypatch.setattr(media_search, "EU_EEA_COUNTRIES", [COUNTRY_BY_ISO2["CZ"]])
    monkeypatch.setattr(media_search.requests, "get", lambda *a, **k: Response())
    monkeypatch.setattr(media_search.time, "sleep", lambda *_: None)
    items, status = media_search.brave_candidates("secret", 365)
    assert status["requests"] == 3
    assert len(items) == 3
    assert items[0]["title"] == "Visa fee"
    assert items[0]["url"] == "https://example.com/fee"


def test_gdelt_client_reads_article_list_json(monkeypatch):
    import media_search
    from sources import COUNTRY_BY_ISO2

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"articles": [{
                "url": "https://news.example/article",
                "title": "Merchant service charge is 1.2%",
                "seendate": "20260701123000",
                "domain": "news.example",
                "language": "Czech",
            }]}

    monkeypatch.setattr(media_search, "EU_EEA_COUNTRIES", [COUNTRY_BY_ISO2["CZ"]])
    monkeypatch.setattr(media_search.requests, "get", lambda *a, **k: Response())
    monkeypatch.setattr(media_search.time, "sleep", lambda *_: None)
    items, status = media_search.gdelt_candidates(400)
    assert status["requests"] == 1
    assert items[0]["published_date"] == "2026-07-01"
    assert items[0]["search_engine"] == "gdelt"
