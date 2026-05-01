import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.config.settings import get_settings
from app.client.telegram import TelegramClientContext
from app.markets.portals import PortalsAuthError, PortalsClient, PortalsFloor, PortalsListing
from app.schemas.market import MarketFloorCreateSchema, MarketListingCreateSchema
from app.storage.database import get_session_factory, init_db
from app.storage.gift_repo import GiftRepository
from app.storage.market_repo import MarketRepository
from app.utils.logging import configure_logging

markets_app = typer.Typer(help="Market research commands")
portals_app = typer.Typer(help="Portals market research")
markets_app.add_typer(portals_app, name="portals")
console = Console()


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
) -> None:
    """Fetch and persist Portals floors for local gift collections."""
    asyncio.run(_portals_sync_floors(from_local, owner_peer, limit))


async def _portals_sync_floors(from_local: bool, owner_peer: str, limit: int) -> None:
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
    try:
        for gift_name in gift_names:
            all_floors.extend(client.filter_floors(gift_name))
    except PortalsAuthError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)

    await _save_floors(settings.db_url, all_floors)
    _render_floors(all_floors)
    typer.echo(f"Synced {len(all_floors)} floor snapshot(s) for {len(gift_names)} gift name(s).")


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
