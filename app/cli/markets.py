import asyncio
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from app.config.settings import get_settings
from app.client.telegram import TelegramClientContext
from app.markets.portals import PortalsApiError, PortalsAuthError, PortalsClient, PortalsFloor, PortalsListing
from app.models.gift import Gift
from app.models.market import MarketFloor
from app.schemas.market import MarketFloorCreateSchema, MarketListingCreateSchema
from app.storage.database import get_session_factory, init_db
from app.storage.gift_repo import GiftRepository
from app.storage.market_repo import MarketRepository
from app.utils.logging import configure_logging

markets_app = typer.Typer(help="Market research commands")
portals_app = typer.Typer(help="Portals market research")
markets_app.add_typer(portals_app, name="portals")
console = Console()


@dataclass(frozen=True)
class PortfolioReportRow:
    gift_id: int | None
    title: str
    slug: str | None
    model: str | None
    backdrop: str | None
    symbol: str | None
    collection_floor_ton: float | None
    model_floor_ton: float | None
    symbol_floor_ton: float | None
    backdrop_floor_ton: float | None
    best_signal: str
    best_floor_ton: float | None
    confidence: str
    action: str


@portals_app.command("auth")
def portals_auth(
    write_env: bool = typer.Option(False, "--write-env", help="Persist PORTALS_AUTH_DATA to .env"),
) -> None:
    """Fetch fresh Portals Telegram Mini App auth data via the current Telegram session."""
    asyncio.run(_portals_auth(write_env))


async def _portals_auth(write_env: bool) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    try:
        async with TelegramClientContext(settings) as tg:
            if not await tg.raw.is_user_authorized():
                typer.echo("Not authenticated. Run: gifts-sales auth login")
                raise typer.Exit(1)
            auth_data = await tg.get_portals_auth_data()
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)

    typer.echo(f"Fetched Portals auth data ({len(auth_data)} chars).")
    if write_env:
        _upsert_env_value(Path(".env"), "PORTALS_AUTH_DATA", auth_data)
        typer.echo("Updated PORTALS_AUTH_DATA in .env.")
    else:
        typer.echo("Run again with --write-env to persist it.")


def _upsert_env_value(path: Path, key: str, value: str) -> None:
    line = f"{key}={value}\n"
    if not path.exists():
        path.write_text(line, encoding="utf-8")
        return
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated = False
    for idx, existing in enumerate(lines):
        if existing.startswith(f"{key}=") or existing.startswith(f"# {key}="):
            lines[idx] = line
            updated = True
            break
    if not updated:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(line)
    path.write_text("".join(lines), encoding="utf-8")


@portals_app.command("search")
def portals_search(
    gift_name: str | None = typer.Option(None, "--gift-name", help="Gift collection name"),
    model: str | None = typer.Option(None, "--model", help="Model filter"),
    backdrop: str | None = typer.Option(None, "--backdrop", help="Backdrop filter"),
    symbol: str | None = typer.Option(None, "--symbol", help="Symbol filter"),
    sort: str = typer.Option("price_asc", "--sort", help="Sort key"),
    limit: int = typer.Option(20, "--limit", help="Result limit"),
    save: bool = typer.Option(False, "--save", help="Persist listings to local DB"),
) -> None:
    """Search listed gifts on Portals."""
    asyncio.run(_portals_search(gift_name, model, backdrop, symbol, sort, limit, save))


async def _portals_search(
    gift_name: str | None,
    model: str | None,
    backdrop: str | None,
    symbol: str | None,
    sort: str,
    limit: int,
    save: bool,
) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    client = PortalsClient(settings.portals_api_base, settings.portals_auth_data)
    try:
        listings = client.search(
            gift_name=gift_name,
            model=model,
            backdrop=backdrop,
            symbol=symbol,
            sort=sort,
            limit=limit,
        )
    except PortalsAuthError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)

    _render_listings(listings)
    if save:
        await init_db(settings.db_url)
        sf = get_session_factory()
        async with sf() as session:
            repo = MarketRepository(session)
            for listing in listings:
                await repo.add_listing(_listing_schema(listing))
            await session.commit()
        typer.echo(f"Saved {len(listings)} listing snapshot(s).")


@portals_app.command("floors")
def portals_floors(
    save: bool = typer.Option(False, "--save", help="Persist floors to local DB"),
) -> None:
    """Fetch Portals collection floors."""
    asyncio.run(_portals_floors(save))


async def _portals_floors(save: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    client = PortalsClient(settings.portals_api_base, settings.portals_auth_data)
    try:
        floors = client.collection_floors()
    except PortalsAuthError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)

    _render_floors(floors)
    if save:
        await _save_floors(settings.db_url, floors)
        typer.echo(f"Saved {len(floors)} floor snapshot(s).")


@portals_app.command("filter-floors")
def portals_filter_floors(
    gift_name: str = typer.Option(..., "--gift-name", help="Gift collection name"),
    save: bool = typer.Option(False, "--save", help="Persist floors to local DB"),
) -> None:
    """Fetch Portals model/backdrop/symbol floors for one gift collection."""
    asyncio.run(_portals_filter_floors(gift_name, save))


async def _portals_filter_floors(gift_name: str, save: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    client = PortalsClient(settings.portals_api_base, settings.portals_auth_data)
    try:
        floors = client.filter_floors(gift_name)
    except PortalsAuthError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)

    _render_floors(floors)
    if save:
        await _save_floors(settings.db_url, floors)
        typer.echo(f"Saved {len(floors)} floor snapshot(s).")


@portals_app.command("sync-floors")
def portals_sync_floors(
    from_local: bool = typer.Option(False, "--from-local", help="Use local self gifts as input"),
    owner_peer: str = typer.Option("self", "--owner-peer", help="Local gift owner peer"),
    limit: int = typer.Option(50, "--limit", help="Max unique gift names to sync"),
    render: bool = typer.Option(False, "--render/--no-render", help="Render every fetched floor row"),
) -> None:
    """Fetch and persist Portals floors for local gift collections."""
    asyncio.run(_portals_sync_floors(from_local, owner_peer, limit, render))


async def _portals_sync_floors(from_local: bool, owner_peer: str, limit: int, render: bool) -> None:
    if not from_local:
        typer.echo("Currently only --from-local is supported.")
        raise typer.Exit(1)

    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    sf = get_session_factory()
    async with sf() as session:
        gifts = await GiftRepository(session).list_all(owner_peer=owner_peer)
    gift_names = sorted({gift.title for gift in gifts if gift.title})[:limit]

    client = PortalsClient(settings.portals_api_base, settings.portals_auth_data)
    all_floors: list[PortalsFloor] = []
    failed: list[tuple[str, str]] = []
    try:
        for gift_name in gift_names:
            try:
                floors = client.filter_floors(gift_name)
            except PortalsApiError as exc:
                failed.append((gift_name, str(exc)))
                continue
            all_floors.extend(floors)
    except PortalsAuthError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)

    await _save_floors(settings.db_url, all_floors)
    if render:
        _render_floors(all_floors)
    _render_sync_summary(gift_names, all_floors, failed)


@portals_app.command("portfolio-report")
def portals_portfolio_report(
    owner_peer: str = typer.Option("self", "--owner-peer", help="Local gift owner peer"),
    limit: int = typer.Option(25, "--limit", help="Rows to show"),
    include_unmatched: bool = typer.Option(
        False,
        "--include-unmatched",
        help="Include local gifts without saved Portals market data",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional CSV/JSON output path"),
    format: str = typer.Option("csv", "--format", help="Export format when --output is used: csv or json"),
) -> None:
    """Show local gifts ranked by the best saved Portals attribute floor."""
    asyncio.run(_portals_portfolio_report(owner_peer, limit, include_unmatched, output, format))


async def _portals_portfolio_report(
    owner_peer: str,
    limit: int,
    include_unmatched: bool,
    output: Path | None,
    format: str,
) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    sf = get_session_factory()
    async with sf() as session:
        gifts = await GiftRepository(session).list_all(owner_peer=owner_peer)
        floors = await MarketRepository(session).latest_floors(market="portals", limit=100_000)

    collection_floor_index = _latest_collection_floor_index(floors)
    floor_index = _latest_floor_index(floors)
    rows = _build_portfolio_report_rows(
        gifts,
        collection_floor_index,
        floor_index,
        include_unmatched=include_unmatched,
    )

    rows.sort(key=lambda row: (row.best_floor_ton is not None, row.best_floor_ton or 0), reverse=True)
    if output is not None:
        _write_portfolio_report(rows, output, format)
        typer.echo(f"Exported {len(rows)} portfolio report row(s) to {output}.")
    _render_portfolio_report(rows[:limit], owner_peer=owner_peer, total_matches=len(rows))


async def _save_floors(db_url: str, floors: list[PortalsFloor]) -> None:
    await init_db(db_url)
    sf = get_session_factory()
    async with sf() as session:
        repo = MarketRepository(session)
        for floor in floors:
            await repo.add_floor(_floor_schema(floor))
        await session.commit()


def _render_listings(listings: list[PortalsListing]) -> None:
    table = Table(title=f"Portals Listings ({len(listings)})")
    table.add_column("ID", style="dim")
    table.add_column("Gift")
    table.add_column("Model")
    table.add_column("Backdrop")
    table.add_column("Symbol")
    table.add_column("Price TON", style="yellow")
    for listing in listings:
        table.add_row(
            listing.external_id or "-",
            listing.gift_name,
            listing.model or "-",
            listing.backdrop or "-",
            listing.symbol or "-",
            f"{listing.price_ton:.4f}" if listing.price_ton is not None else "-",
        )
    console.print(table)


def _render_floors(floors: list[PortalsFloor]) -> None:
    table = Table(title=f"Portals Floors ({len(floors)})")
    table.add_column("Gift")
    table.add_column("Model")
    table.add_column("Backdrop")
    table.add_column("Symbol")
    table.add_column("Floor TON", style="yellow")
    for floor in floors:
        table.add_row(
            floor.gift_name,
            floor.model or "-",
            floor.backdrop or "-",
            floor.symbol or "-",
            f"{floor.floor_price_ton:.4f}" if floor.floor_price_ton is not None else "-",
        )
    console.print(table)


def _render_sync_summary(
    gift_names: list[str],
    floors: list[PortalsFloor],
    failed: list[tuple[str, str]],
) -> None:
    by_gift: dict[str, int] = {}
    for floor in floors:
        by_gift[floor.gift_name] = by_gift.get(floor.gift_name, 0) + 1

    table = Table(title="Portals Floor Sync Summary")
    table.add_column("Metric")
    table.add_column("Value", style="yellow")
    table.add_row("Gift collections requested", str(len(gift_names)))
    table.add_row("Collections with floors", str(len(by_gift)))
    table.add_row("Floor rows saved", str(len(floors)))
    table.add_row("Failed collections", str(len(failed)))
    console.print(table)

    if failed:
        failed_table = Table(title="Failed Collections")
        failed_table.add_column("Gift")
        failed_table.add_column("Error")
        for gift_name, error in failed[:20]:
            failed_table.add_row(gift_name, error[:160])
        console.print(failed_table)


def _render_portfolio_report(
    rows: list[PortfolioReportRow],
    *,
    owner_peer: str,
    total_matches: int,
) -> None:
    table = Table(title=f"Portals Portfolio Report: {owner_peer} ({total_matches} matches)")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Gift")
    table.add_column("Attributes")
    table.add_column("Floors TON\nC / M / S / B", style="yellow")
    table.add_column("Best", no_wrap=True)
    table.add_column("Conf", no_wrap=True)
    table.add_column("Next")
    for row in rows:
        table.add_row(
            str(row.gift_id or "-"),
            _gift_label(row),
            _attribute_label(row),
            _floor_label(row),
            f"{row.best_signal} {_format_ton(row.best_floor_ton)}",
            row.confidence,
            row.action,
        )
    console.print(table)


def _floor_schema(floor: PortalsFloor) -> MarketFloorCreateSchema:
    return MarketFloorCreateSchema(
        market="portals",
        gift_name=floor.gift_name,
        model=floor.model,
        backdrop=floor.backdrop,
        symbol=floor.symbol,
        floor_price_ton=floor.floor_price_ton,
        listed_count=floor.listed_count,
        raw_json=json.dumps(floor.raw or {}, ensure_ascii=False),
    )


def _listing_schema(listing: PortalsListing) -> MarketListingCreateSchema:
    return MarketListingCreateSchema(
        market="portals",
        external_id=listing.external_id,
        tg_id=listing.tg_id,
        gift_name=listing.gift_name,
        model=listing.model,
        backdrop=listing.backdrop,
        symbol=listing.symbol,
        price_ton=listing.price_ton,
        raw_json=json.dumps(listing.raw, ensure_ascii=False),
    )


def _latest_floor_index(floors: list[MarketFloor]) -> dict[tuple[str, str, str], MarketFloor]:
    index: dict[tuple[str, str, str], MarketFloor] = {}
    for floor in sorted(floors, key=lambda item: (item.captured_at, item.id)):
        if floor.model:
            index[(_norm(floor.gift_name), "model", _norm(floor.model))] = floor
        if floor.backdrop:
            index[(_norm(floor.gift_name), "backdrop", _norm(floor.backdrop))] = floor
        if floor.symbol:
            index[(_norm(floor.gift_name), "symbol", _norm(floor.symbol))] = floor
    return index


def _latest_collection_floor_index(floors: list[MarketFloor]) -> dict[str, MarketFloor]:
    index: dict[str, MarketFloor] = {}
    for floor in sorted(floors, key=lambda item: (item.captured_at, item.id)):
        if not floor.model and not floor.backdrop and not floor.symbol:
            index[_collection_norm(floor.gift_name)] = floor
    return index


def _build_portfolio_report_rows(
    gifts: list[Gift],
    collection_floor_index: dict[str, MarketFloor],
    floor_index: dict[tuple[str, str, str], MarketFloor],
    *,
    include_unmatched: bool = False,
) -> list[PortfolioReportRow]:
    rows: list[PortfolioReportRow] = []
    for gift in gifts:
        row = _build_portfolio_report_row(
            gift,
            collection_floor_index,
            floor_index,
            include_unmatched=include_unmatched,
        )
        if row is not None:
            rows.append(row)
    return rows


def _build_portfolio_report_row(
    gift: Gift,
    collection_floor_index: dict[str, MarketFloor],
    floor_index: dict[tuple[str, str, str], MarketFloor],
    *,
    include_unmatched: bool = False,
) -> PortfolioReportRow | None:
    if not gift.title:
        if not include_unmatched:
            return None
        return PortfolioReportRow(
            gift_id=gift.id,
            title="-",
            slug=gift.slug,
            model=None,
            backdrop=None,
            symbol=None,
            collection_floor_ton=None,
            model_floor_ton=None,
            symbol_floor_ton=None,
            backdrop_floor_ton=None,
            best_signal="none",
            best_floor_ton=None,
            confidence="unknown",
            action="missing gift title",
        )

    attrs = _gift_attributes(gift)
    collection_floor = collection_floor_index.get(_collection_norm(gift.title))
    model_floor = _attribute_floor(gift.title, "model", attrs.get("model"), floor_index)
    symbol_floor = _attribute_floor(gift.title, "symbol", attrs.get("symbol"), floor_index)
    backdrop_floor = _attribute_floor(gift.title, "backdrop", attrs.get("backdrop"), floor_index)

    candidates = [
        ("collection", _floor_ton(collection_floor)),
        ("model", _floor_ton(model_floor)),
        ("symbol", _floor_ton(symbol_floor)),
        ("backdrop", _floor_ton(backdrop_floor)),
    ]
    candidates = [(source, value) for source, value in candidates if value is not None]
    if not candidates:
        if not include_unmatched:
            return None
        return PortfolioReportRow(
            gift_id=gift.id,
            title=gift.title,
            slug=gift.slug,
            model=attrs.get("model"),
            backdrop=attrs.get("backdrop"),
            symbol=attrs.get("symbol"),
            collection_floor_ton=None,
            model_floor_ton=None,
            symbol_floor_ton=None,
            backdrop_floor_ton=None,
            best_signal="none",
            best_floor_ton=None,
            confidence="unknown",
            action="sync market data",
        )

    best_signal, best_floor_ton = max(candidates, key=lambda item: item[1])
    confidence = _confidence_for_signal(
        best_signal,
        model_floor_ton=_floor_ton(model_floor),
        symbol_floor_ton=_floor_ton(symbol_floor),
        backdrop_floor_ton=_floor_ton(backdrop_floor),
    )
    return PortfolioReportRow(
        gift_id=gift.id,
        title=gift.title,
        slug=gift.slug,
        model=attrs.get("model"),
        backdrop=attrs.get("backdrop"),
        symbol=attrs.get("symbol"),
        collection_floor_ton=_floor_ton(collection_floor),
        model_floor_ton=_floor_ton(model_floor),
        symbol_floor_ton=_floor_ton(symbol_floor),
        backdrop_floor_ton=_floor_ton(backdrop_floor),
        best_signal=best_signal,
        best_floor_ton=best_floor_ton,
        confidence=confidence,
        action=_action_for_confidence(confidence),
    )


def _attribute_floor(
    gift_name: str,
    source: str,
    value: str | None,
    floor_index: dict[tuple[str, str, str], MarketFloor],
) -> MarketFloor | None:
    if not value:
        return None
    return floor_index.get((_norm(gift_name), source, _norm(value)))


def _floor_ton(floor: MarketFloor | None) -> float | None:
    if floor is None:
        return None
    return floor.floor_price_ton


def _confidence_for_signal(
    best_signal: str,
    *,
    model_floor_ton: float | None,
    symbol_floor_ton: float | None,
    backdrop_floor_ton: float | None,
) -> str:
    if best_signal == "model":
        return "high"
    attribute_values = [
        value for value in (model_floor_ton, symbol_floor_ton, backdrop_floor_ton) if value is not None
    ]
    best_attribute = max(attribute_values) if attribute_values else None
    supporting_attributes = 0
    if best_attribute:
        supporting_attributes = sum(value >= best_attribute * 0.8 for value in attribute_values)
    if supporting_attributes >= 2:
        return "high"
    if best_signal in {"symbol", "backdrop"}:
        return "medium"
    return "low"


def _action_for_confidence(confidence: str) -> str:
    if confidence == "high":
        return "verify exact listing"
    if confidence == "medium":
        return "check exact listing"
    return "sync more data"


def _write_portfolio_report(rows: list[PortfolioReportRow], output: Path, format: str) -> None:
    normalized_format = format.lower()
    data = [_portfolio_row_dict(row) for row in rows]
    output.parent.mkdir(parents=True, exist_ok=True)
    if normalized_format == "json":
        output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    if normalized_format == "csv":
        with output.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=PORTFOLIO_REPORT_FIELDS)
            writer.writeheader()
            writer.writerows(data)
        return
    typer.echo("Unknown format. Valid: csv, json")
    raise typer.Exit(1)


PORTFOLIO_REPORT_FIELDS = [
    "gift_id",
    "title",
    "slug",
    "model",
    "backdrop",
    "symbol",
    "collection_floor_ton",
    "model_floor_ton",
    "symbol_floor_ton",
    "backdrop_floor_ton",
    "best_signal",
    "best_floor_ton",
    "confidence",
    "action",
]


def _portfolio_row_dict(row: PortfolioReportRow) -> dict[str, Any]:
    return {
        "gift_id": row.gift_id,
        "title": row.title,
        "slug": row.slug,
        "model": row.model,
        "backdrop": row.backdrop,
        "symbol": row.symbol,
        "collection_floor_ton": row.collection_floor_ton,
        "model_floor_ton": row.model_floor_ton,
        "symbol_floor_ton": row.symbol_floor_ton,
        "backdrop_floor_ton": row.backdrop_floor_ton,
        "best_signal": row.best_signal,
        "best_floor_ton": row.best_floor_ton,
        "confidence": row.confidence,
        "action": row.action,
    }


def _best_floor_match(
    gift_name: str,
    attrs: dict[str, str],
    floor_index: dict[tuple[str, str, str], MarketFloor],
) -> tuple[MarketFloor, str] | None:
    matches: list[tuple[MarketFloor, str]] = []
    for source in ("model", "symbol", "backdrop"):
        value = attrs.get(source)
        if not value:
            continue
        floor = floor_index.get((_norm(gift_name), source, _norm(value)))
        if floor is not None:
            matches.append((floor, source))
    if not matches:
        return None
    return max(matches, key=lambda item: item[0].floor_price_ton or 0)


def _gift_attributes(gift: Gift) -> dict[str, str]:
    if not gift.raw_json:
        return {}
    try:
        raw = json.loads(gift.raw_json)
    except json.JSONDecodeError:
        return {}
    raw_attrs = (((raw.get("gift") or {}).get("attributes")) if isinstance(raw, dict) else None) or []
    attrs: dict[str, str] = {}
    for item in raw_attrs:
        if not isinstance(item, dict):
            continue
        key = _attribute_key(item.get("_"))
        name = item.get("name")
        if key and isinstance(name, str) and name:
            attrs[key] = name
    return attrs


def _attribute_key(raw_type: Any) -> str | None:
    if raw_type == "StarGiftAttributeModel":
        return "model"
    if raw_type == "StarGiftAttributeBackdrop":
        return "backdrop"
    if raw_type == "StarGiftAttributePattern":
        return "symbol"
    return None


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _collection_norm(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _format_ton(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else "-"


def _gift_label(row: PortfolioReportRow) -> str:
    if row.slug:
        return f"{row.title}\n{row.slug}"
    return row.title


def _attribute_label(row: PortfolioReportRow) -> str:
    return "\n".join(
        [
            f"M: {row.model or '-'}",
            f"S: {row.symbol or '-'}",
            f"B: {row.backdrop or '-'}",
        ]
    )


def _floor_label(row: PortfolioReportRow) -> str:
    return " / ".join(
        [
            _format_ton(row.collection_floor_ton),
            _format_ton(row.model_floor_ton),
            _format_ton(row.symbol_floor_ton),
            _format_ton(row.backdrop_floor_ton),
        ]
    )
