import argparse
import bisect
from collections import Counter
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Optional

from venues.jupiter_prediction import JupiterAuthError, JupiterPredictionVenue

MICRO_USD = 1_000_000
PROVIDERS = ("polymarket", "kalshi")

@dataclass(frozen=True)
class MarketRef:
    provider: str
    event_id: str
    market_id: str
    event_title: str
    market_title: str
    rules: str
    close_time: Optional[float]
    opened_at: Optional[float]
    buy_yes: Optional[float]
    buy_no: Optional[float]
    volume: Optional[float]
    category: str = ""


def first_value(row: dict, keys: tuple[str, ...]) -> Any:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
        value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def text_value(row: dict, keys: tuple[str, ...]) -> str:
    value = first_value(row, keys)
    return str(value).strip() if value not in (None, "") else ""


def parse_time(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value / 1000 if value > 10_000_000_000 else value)
    raw = str(value).strip()
    if raw.isdigit():
        number = float(raw)
        return number / 1000 if number > 10_000_000_000 else number
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def normalized(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", plain.lower()))


def threshold_tokens(ref: MarketRef) -> set[str]:
    text = f"{ref.market_title} {ref.rules}"
    patterns = (
        r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)",
        r"\b(?:above|below|over|under|higher|lower|at least|less than|more than|reach)\s+\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)",
        r"^[^\d]*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b",
    )
    values = {value.replace(",", "") for pattern in patterns for value in re.findall(pattern, text, flags=re.IGNORECASE)}
    return values


def price_usd(pricing: Any, field: str) -> Optional[float]:
    if not isinstance(pricing, dict) or pricing.get(field) is None:
        return None
    try:
        return float(pricing[field]) / MICRO_USD
    except (TypeError, ValueError):
        return None


def numeric_value(row: Any, field: str) -> Optional[float]:
    if not isinstance(row, dict) or row.get(field) is None:
        return None
    try:
        return float(row[field])
    except (TypeError, ValueError):
        return None


def opened_at(row: dict) -> Optional[float]:
    return parse_time(first_value(row, ("openTime", "open_time", "createdAt", "created_at")))


def iso_time(value: Optional[float]) -> Optional[str]:
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


def event_fields(event: dict) -> tuple[str, str, Optional[float]]:
    title = text_value(event, ("title", "question", "name", "eventTitle"))
    rules = text_value(event, ("rulesPrimary", "rulesSecondary", "resolutionSource", "description"))
    close = parse_time(first_value(event, ("closeTime", "close_time", "endTime", "endDate", "resolveAt")))
    return title, rules, close


def is_tradable(row: dict, now: float) -> bool:
    active = first_value(row, ("isActive", "active"))
    if active is False or str(active).lower() == "false":
        return False
    tradable = first_value(row, ("tradable", "isTradable"))
    if tradable is False or str(tradable).lower() == "false":
        return False
    status = text_value(row, ("status",)).lower()
    if status in {"closed", "resolved", "settled", "cancelled", "canceled", "inactive"}:
        return False
    result = first_value(row, ("result",))
    if result not in (None, "") and str(result).lower() != "pending":
        return False
    close = parse_time(first_value(row, ("closeTime", "close_time", "endTime", "endDate", "resolveAt")))
    return close is None or close > now


def market_refs(provider: str, events: list[dict]) -> list[MarketRef]:
    refs: list[MarketRef] = []
    now = time.time()
    for event in events:
        if not is_tradable(event, now):
            continue
        event_id = str(first_value(event, ("eventId", "id", "ticker")) or "")
        if not event_id:
            continue
        event_title, event_rules, event_close = event_fields(event)
        event_opened_at = opened_at(event)
        markets = event.get("markets") if isinstance(event.get("markets"), list) else []
        for market in markets:
            if not is_tradable(market, now):
                continue
            market_id = str(first_value(market, ("marketId", "id", "ticker")) or "")
            if not market_id:
                continue
            market_title = text_value(market, ("title", "question", "name"))
            market_rules = text_value(market, ("rulesPrimary", "rulesSecondary", "resolutionSource", "description"))
            market_close = parse_time(first_value(market, ("closeTime", "close_time", "endTime", "endDate", "resolveAt")))
            pricing = market.get("pricing")
            refs.append(
                MarketRef(
                    provider=provider,
                    event_id=event_id,
                    category=text_value(event, ("category",)),
                    market_id=market_id,
                    event_title=event_title,
                    market_title=market_title,
                    rules=market_rules or event_rules,
                    close_time=market_close if market_close is not None else event_close,
                    opened_at=opened_at(market) or event_opened_at,
                    buy_yes=price_usd(pricing, "buyYesPriceUsd"),
                    buy_no=price_usd(pricing, "buyNoPriceUsd"),
                    volume=numeric_value(pricing, "volume"),
                )
            )
    return refs


def recent_event_rows(refs: list[MarketRef], recent_hours: float, limit: int) -> list[dict]:
    if recent_hours <= 0 or limit <= 0:
        return []
    now = time.time()
    cutoff = now - recent_hours * 3600
    groups: dict[tuple[str, str], list[MarketRef]] = {}
    for ref in refs:
        if ref.opened_at is None or not cutoff <= ref.opened_at <= now:
            continue
        groups.setdefault((ref.provider, ref.event_id), []).append(ref)
    rows: list[dict] = []
    for event_refs in groups.values():
        ordered = sorted(event_refs, key=lambda ref: (ref.volume or 0.0, ref.market_title), reverse=True)
        representative = ordered[0]
        rows.append(
            {
                "provider": representative.provider,
                "category": representative.category,
                "event_id": representative.event_id,
                "event_title": representative.event_title,
                "opened_at": iso_time(max(ref.opened_at for ref in event_refs if ref.opened_at is not None)),
                "close_time": iso_time(representative.close_time),
                "active_market_count": len(event_refs),
                "max_volume_raw": max(ref.volume or 0.0 for ref in event_refs),
                "sample_markets": [
                    {
                        "market_id": ref.market_id,
                        "title": ref.market_title,
                        "buy_yes_usd": ref.buy_yes,
                        "buy_no_usd": ref.buy_no,
                        "volume_raw": ref.volume,
                    }
                    for ref in ordered[:4]
                ],
            }
        )
    return sorted(rows, key=lambda row: row["opened_at"] or "", reverse=True)[:limit]


def detail_event(payload: dict) -> dict:
    nested = payload.get("event") if isinstance(payload.get("event"), dict) else None
    return nested or payload


def enrich_refs(venue: JupiterPredictionVenue, refs: list[MarketRef], event_limit: int) -> tuple[list[MarketRef], list[dict]]:
    if event_limit <= 0:
        return refs, []
    cache: dict[tuple[str, str], dict] = {}
    errors: list[dict] = []
    for provider in PROVIDERS:
        event_ids = list(dict.fromkeys(ref.event_id for ref in refs if ref.provider == provider))[:event_limit]
        for event_id in event_ids:
            try:
                cache[(provider, event_id)] = detail_event(venue.get_event(event_id))
            except Exception as error:
                errors.append({"provider": provider, "event_id": event_id, "error": str(error)[:240]})
    enriched: list[MarketRef] = []
    for ref in refs:
        event = cache.get((ref.provider, ref.event_id))
        if not event:
            enriched.append(ref)
            continue
        event_title, event_rules, event_close = event_fields(event)
        event_opened_at = opened_at(event)
        markets = event.get("markets") if isinstance(event.get("markets"), list) else []
        market = next((item for item in markets if str(first_value(item, ("marketId", "id", "ticker")) or "") == ref.market_id), {})
        market_title = text_value(market, ("title", "question", "name")) or ref.market_title
        market_rules = text_value(market, ("rulesPrimary", "rulesSecondary", "resolutionSource", "description"))
        market_close = parse_time(first_value(market, ("closeTime", "close_time", "endTime", "endDate", "resolveAt")))
        pricing = market.get("pricing") if isinstance(market, dict) else None
        enriched.append(
            replace(
                ref,
                event_title=event_title or ref.event_title,
                market_title=market_title,
                rules=market_rules or event_rules or ref.rules,
                close_time=market_close if market_close is not None else event_close if event_close is not None else ref.close_time,
                opened_at=opened_at(market) or event_opened_at or ref.opened_at,
                buy_yes=price_usd(pricing, "buyYesPriceUsd") if price_usd(pricing, "buyYesPriceUsd") is not None else ref.buy_yes,
                buy_no=price_usd(pricing, "buyNoPriceUsd") if price_usd(pricing, "buyNoPriceUsd") is not None else ref.buy_no,
                volume=numeric_value(pricing, "volume") if numeric_value(pricing, "volume") is not None else ref.volume,
            )
        )
    return enriched, errors


def similarity(value_a: str, value_b: str) -> float:
    if not value_a or not value_b:
        return 0.0
    return round(SequenceMatcher(None, normalized(value_a), normalized(value_b)).ratio(), 6)


def scope_conflict(left: MarketRef, right: MarketRef) -> bool:
    left_text = normalized(f"{left.event_title} {left.rules}")
    right_text = normalized(f"{right.event_title} {right.rules}")
    groups = (
        ("vice", ("vice", "vp")),
        ("presidential", ("presidential",)),
        ("senate", ("senate",)),
        ("house", ("house",)),
        ("governor", ("governor",)),
        ("democratic", ("democratic", "democrat")),
        ("republican", ("republican", "gop")),
        ("winner", ("winner", "wins", "win")),
        ("nominee", ("nominee", "nomination")),
    )
    left_groups = {name for name, terms in groups if any(re.search(rf"\b{term}\b", left_text) for term in terms)}
    right_groups = {name for name, terms in groups if any(re.search(rf"\b{term}\b", right_text) for term in terms)}
    exclusive_pairs = (("vice", "presidential"), ("winner", "nominee"), ("senate", "house"), ("democratic", "republican"))
    return any((a in left_groups and b in right_groups) or (b in left_groups and a in right_groups) for a, b in exclusive_pairs)


def same_numbers(left: MarketRef, right: MarketRef) -> bool:
    left_thresholds = threshold_tokens(left)
    right_thresholds = threshold_tokens(right)
    return not left_thresholds or not right_thresholds or bool(left_thresholds & right_thresholds)


def market_signal(ref: MarketRef) -> tuple[Optional[str], Optional[str]]:
    text = normalized(f"{ref.market_title} {ref.rules}")
    assets = {"bitcoin": "btc", "btc": "btc", "ethereum": "eth", "eth": "eth", "solana": "sol", "sol": "sol", "xrp": "xrp", "dogecoin": "doge", "doge": "doge"}
    asset = next((canonical for token, canonical in assets.items() if re.search(rf"\b{token}\b", text)), None)
    if "↑" in ref.market_title:
        return asset, "high"
    if "↓" in ref.market_title:
        return asset, "low"
    high = bool(re.search(r"\b(above|over|higher|at least|reach|up)\b", text))
    low = bool(re.search(r"\b(below|under|lower|less|down)\b", text))
    return asset, "high" if high and not low else "low" if low and not high else None


def close_delta(left: MarketRef, right: MarketRef) -> Optional[float]:
    if left.close_time is None or right.close_time is None:
        return None
    return abs(left.close_time - right.close_time)


def pair_rows(refs: list[MarketRef], min_similarity: float, max_close_delta_s: float, buffer_usd: float) -> list[dict]:
    poly = [ref for ref in refs if ref.provider == "polymarket" and ref.close_time is not None]
    kalshi = sorted((ref for ref in refs if ref.provider == "kalshi" and ref.close_time is not None), key=lambda ref: ref.close_time)
    close_times = [ref.close_time for ref in kalshi]
    rows: list[dict] = []
    for left in poly:
        low = bisect.bisect_left(close_times, left.close_time - max_close_delta_s)
        high = bisect.bisect_right(close_times, left.close_time + max_close_delta_s)
        for right in kalshi[low:high]:
            market_similarity = similarity(left.market_title, right.market_title)
            event_similarity = similarity(left.event_title, right.event_title)
            rules_similarity = similarity(left.rules, right.rules)
            scope_similarity = max(event_similarity, rules_similarity)
            delta = close_delta(left, right)
            left_asset, left_direction = market_signal(left)
            right_asset, right_direction = market_signal(right)
            if delta is None or delta > max_close_delta_s or market_similarity < 0.95 or scope_similarity < min_similarity or not same_numbers(left, right):
                continue
            if scope_conflict(left, right):
                continue
            if left_asset and right_asset and left_asset != right_asset:
                continue
            if left_direction and right_direction and left_direction != right_direction:
                continue
            exact_text = bool(left.market_title and right.market_title and normalized(left.market_title) == normalized(right.market_title))
            exact_rules = bool(left.rules and right.rules and normalized(left.rules) == normalized(right.rules))
            exact_close = delta <= max_close_delta_s
            for yes_ref, no_ref in ((left, right), (right, left)):
                if yes_ref.buy_yes is None or no_ref.buy_no is None:
                    continue
                raw_cost = yes_ref.buy_yes + no_ref.buy_no
                raw_edge = 1.0 - raw_cost
                rows.append(
                    {
                        "yes_provider": yes_ref.provider,
                        "yes_market_id": yes_ref.market_id,
                        "yes_event_id": yes_ref.event_id,
                        "no_provider": no_ref.provider,
                        "no_market_id": no_ref.market_id,
                        "no_event_id": no_ref.event_id,
                        "event_titles": {"polymarket": left.event_title, "kalshi": right.event_title},
                        "market_titles": {"polymarket": left.market_title, "kalshi": right.market_title},
                        "market_title_similarity": market_similarity,
                        "event_title_similarity": event_similarity,
                        "rules_similarity": rules_similarity,
                        "scope_similarity": scope_similarity,
                        "asset": left_asset or right_asset,
                        "direction": left_direction or right_direction,
                        "close_time_delta_s": delta,
                        "strict_semantic_match": exact_text and exact_rules and exact_close,
                        "raw_cost_usd_per_contract": round(raw_cost, 6),
                        "raw_edge_usd_per_contract": round(raw_edge, 6),
                        "passes_conservative_buffer_pre_fee_quote": raw_edge >= buffer_usd,
                        "status": "manual_rule_and_fee_quote_required",
                    }
                )
    return sorted(rows, key=lambda row: row["raw_edge_usd_per_contract"], reverse=True)


def pair_gate_diagnostics(refs: list[MarketRef], min_similarity: float, max_close_delta_s: float) -> dict[str, Any]:
    poly = [ref for ref in refs if ref.provider == "polymarket" and ref.close_time is not None]
    kalshi = sorted((ref for ref in refs if ref.provider == "kalshi" and ref.close_time is not None), key=lambda ref: ref.close_time)
    close_times = [ref.close_time for ref in kalshi]
    nearest_close_delta_s: Optional[float] = None
    for left in poly:
        index = bisect.bisect_left(close_times, left.close_time)
        for candidate_index in (index - 1, index):
            if 0 <= candidate_index < len(kalshi):
                delta = abs(left.close_time - kalshi[candidate_index].close_time)
                if nearest_close_delta_s is None or delta < nearest_close_delta_s:
                    nearest_close_delta_s = delta
    counts: Counter[str] = Counter()
    for left in poly:
        low = bisect.bisect_left(close_times, left.close_time - max_close_delta_s)
        high = bisect.bisect_right(close_times, left.close_time + max_close_delta_s)
        for right in kalshi[low:high]:
            counts["close_window_pairs"] += 1
            market_similarity = similarity(left.market_title, right.market_title)
            if market_similarity < 0.95:
                continue
            counts["market_title_matches"] += 1
            event_similarity = similarity(left.event_title, right.event_title)
            rules_similarity = similarity(left.rules, right.rules)
            if max(event_similarity, rules_similarity) < min_similarity:
                continue
            counts["scope_matches"] += 1
            if not same_numbers(left, right):
                continue
            counts["number_compatible_matches"] += 1
            if scope_conflict(left, right):
                continue
            counts["scope_compatible_matches"] += 1
            left_asset, left_direction = market_signal(left)
            right_asset, right_direction = market_signal(right)
            if left_asset and right_asset and left_asset != right_asset:
                continue
            counts["asset_compatible_matches"] += 1
            if left_direction and right_direction and left_direction != right_direction:
                continue
            counts["direction_compatible_matches"] += 1
            counts["semantic_matches_before_quote"] += 1
            for yes_ref, no_ref in ((left, right), (right, left)):
                if yes_ref.buy_yes is not None and no_ref.buy_no is not None:
                    counts["quoted_orientations"] += 1
    return {
        "polymarket_markets_with_close_time": len(poly),
        "kalshi_markets_with_close_time": len(kalshi),
        "polymarket_close_time_range": {
            "earliest": iso_time(min(ref.close_time for ref in poly)) if poly else None,
            "latest": iso_time(max(ref.close_time for ref in poly)) if poly else None,
        },
        "kalshi_close_time_range": {
            "earliest": iso_time(min(ref.close_time for ref in kalshi)) if kalshi else None,
            "latest": iso_time(max(ref.close_time for ref in kalshi)) if kalshi else None,
        },
        "nearest_cross_provider_close_delta_s": round(nearest_close_delta_s, 3) if nearest_close_delta_s is not None else None,
        **{
            name: counts[name]
            for name in (
                "close_window_pairs",
                "market_title_matches",
                "scope_matches",
                "number_compatible_matches",
                "scope_compatible_matches",
                "asset_compatible_matches",
                "direction_compatible_matches",
                "semantic_matches_before_quote",
                "quoted_orientations",
            )
        },
    }


def pagination_has_next(pagination: dict, batch: list[dict], page_size: int) -> bool:
    has_next = pagination.get("hasNext") if isinstance(pagination, dict) else None
    if has_next is None:
        return len(batch) >= page_size
    return has_next is True or str(has_next).lower() in {"1", "true", "yes"}


def fetch_events(
    venue: JupiterPredictionVenue,
    provider: str,
    categories: list[str],
    event_filters: list[Optional[str]],
    pages: int,
    page_size: int,
    delay_s: float,
    page_attempts: int,
    retry_delay_s: float,
    include_all_markets: bool,
    sort_by: Optional[str],
    sort_direction: Optional[str],
) -> tuple[list[dict], list[dict], bool, dict[str, dict]]:
    events: list[dict] = []
    errors: list[dict] = []
    coverage: dict[str, dict] = {}
    seen_event_ids: set[str] = set()
    reached_end = True
    for category in categories:
        for event_filter in event_filters:
            scope = f"{category}:{event_filter or 'unfiltered'}"
            scope_reached_end = False
            pages_fetched = 0
            total = None
            for page in range(pages):
                batch = None
                pagination: dict = {}
                last_error = None
                for attempt in range(page_attempts):
                    try:
                        batch, pagination = venue.list_events_page(
                            category=category,
                            provider=provider,
                            event_filter=event_filter,
                            include_markets=True,
                            include_all_markets=include_all_markets,
                            sort_by=sort_by,
                            sort_direction=sort_direction,
                            start=page * page_size,
                            limit=page_size,
                        )
                        break
                    except Exception as error:
                        last_error = error
                        if attempt + 1 < page_attempts and retry_delay_s > 0:
                            time.sleep(retry_delay_s)
                if batch is None:
                    errors.append(
                        {
                            "provider": provider,
                            "category": category,
                            "filter": event_filter,
                            "page": page,
                            "attempts": page_attempts,
                            "error": str(last_error)[:240],
                        }
                    )
                    continue
                pages_fetched += 1
                total = pagination.get("total", total) if isinstance(pagination, dict) else total
                for event in (item for item in batch if isinstance(item, dict)):
                    event_id = str(first_value(event, ("eventId", "id", "ticker")) or "")
                    identity = event_id or json.dumps(event, sort_keys=True, default=str)
                    if identity not in seen_event_ids:
                        seen_event_ids.add(identity)
                        events.append(event)
                if not pagination_has_next(pagination, batch, page_size):
                    scope_reached_end = True
                    break
                if delay_s > 0:
                    time.sleep(delay_s)
            coverage[scope] = {"pages_fetched": pages_fetched, "reported_total": total, "reached_end": scope_reached_end}
            reached_end = reached_end and scope_reached_end
    return events, errors, reached_end, coverage

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--page-delay-s", type=float, default=0.5)
    parser.add_argument("--page-attempts", type=int, default=1)
    parser.add_argument("--retry-delay-s", type=float, default=3.0)
    parser.add_argument("--live-only", action="store_true")
    parser.add_argument("--event-filter", action="append", choices=("live", "upcoming", "new", "trending"))
    parser.add_argument("--include-all-markets", action="store_true")
    parser.add_argument("--sort-by", choices=("volume", "beginAt"), default="beginAt")
    parser.add_argument("--sort-direction", choices=("asc", "desc"), default="asc")
    parser.add_argument("--recent-hours", type=float, default=24.0)
    parser.add_argument("--recent-limit", type=int, default=10)
    parser.add_argument("--detail-events-per-provider", type=int, default=0)
    parser.add_argument("--min-similarity", type=float, default=0.97)
    parser.add_argument("--max-close-delta-s", type=float, default=300.0)
    parser.add_argument("--conservative-buffer-usd", type=float, default=0.05)
    parser.add_argument("--pair-diagnostics", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    if args.live_only and args.event_filter and any(event_filter != "live" for event_filter in args.event_filter):
        parser.error("--live-only nao pode ser combinado com filtros diferentes de live")
    categories = args.category or ["crypto"]
    event_filters = list(dict.fromkeys(args.event_filter or (["live"] if args.live_only else [None])))
    venue = JupiterPredictionVenue()
    source_events: dict[str, list[dict]] = {}
    source_errors: dict[str, list[dict]] = {}
    source_reached_end: dict[str, bool] = {}
    source_coverage: dict[str, dict[str, dict]] = {}
    for provider in PROVIDERS:
        events, errors, reached_end, coverage = fetch_events(
            venue,
            provider,
            categories,
            event_filters,
            max(1, args.pages),
            max(1, args.page_size),
            max(0.0, args.page_delay_s),
            max(1, args.page_attempts),
            max(0.0, args.retry_delay_s),
            args.include_all_markets,
            args.sort_by,
            args.sort_direction,
        )
        source_events[provider] = events
        source_errors[provider] = errors
        source_reached_end[provider] = reached_end
        source_coverage[provider] = coverage
    refs = [ref for provider in PROVIDERS for ref in market_refs(provider, source_events[provider])]
    refs, detail_errors = enrich_refs(venue, refs, max(0, args.detail_events_per_provider))
    max_close_delta_s = max(0.0, args.max_close_delta_s)
    rows = pair_rows(refs, args.min_similarity, max_close_delta_s, max(0.0, args.conservative_buffer_usd))
    pair_diagnostics = pair_gate_diagnostics(refs, args.min_similarity, max_close_delta_s) if args.pair_diagnostics else None
    collection_complete = all(
        source_events[provider]
        and source_reached_end[provider]
        and not source_errors[provider]
        and any(ref.provider == provider for ref in refs)
        for provider in PROVIDERS
    )
    report = {
        "read_only": True,
        "orders_created": False,
        "orders_submitted": False,
        "collection_status": "complete" if collection_complete else "inconclusive_partial_source_data",
        "categories": categories,
        "live_only": args.live_only,
        "event_filters": event_filters,
        "include_all_markets": args.include_all_markets,
        "sort": {"by": args.sort_by, "direction": args.sort_direction},
        "conservative_buffer_usd_per_contract": args.conservative_buffer_usd,
        "source_status": {
            provider: {
                "events": len(source_events[provider]),
                "markets": sum(1 for ref in refs if ref.provider == provider),
                "reached_end": source_reached_end[provider],
                "filter_coverage": source_coverage[provider],
                "categories": dict(sorted(Counter(ref.category for ref in refs if ref.provider == provider).items())),
                "errors": source_errors[provider],
            }
            for provider in PROVIDERS
        },
        "detail_errors": detail_errors,
        "pair_diagnostics": pair_diagnostics,
        "recent_event_hours": max(0.0, args.recent_hours),
        "recent_events": recent_event_rows(refs, max(0.0, args.recent_hours), max(0, args.recent_limit)),
        "candidate_matches": len(rows),
        "strict_semantic_matches": sum(1 for row in rows if row["strict_semantic_match"]),
        "candidate_pre_fee_buffer_passes": sum(1 for row in rows if row["passes_conservative_buffer_pre_fee_quote"]),
        "strict_pre_fee_buffer_passes": sum(1 for row in rows if row["strict_semantic_match"] and row["passes_conservative_buffer_pre_fee_quote"]),
        "pairs": rows[: max(0, args.limit)],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if collection_complete else 2

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except JupiterAuthError as error:
        print(json.dumps({"read_only": True, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
