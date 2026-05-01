import asyncio
import csv
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.config.settings import get_settings
from app.client.telegram import TelegramClientContext
from app.models.gift import Gift
from app.models.approval import ApprovalAction, ApprovalStatus
from app.models.job import JobStatus, JobType
from app.schemas.approval import ApprovalCreateSchema
from app.schemas.rule import Rule
from app.schemas.job import JobCreateSchema
from app.storage.database import get_session_factory, init_db
from app.storage.approval_repo import ApprovalRepository
from app.storage.gift_repo import GiftRepository
from app.storage.job_repo import JobRepository
from app.services.inventory import InventoryService
from app.services.approval_notifier import ApprovalNotifier
from app.services.listing import ListingService
from app.services.pricing import PricingService
from app.services.transfer import TransferService
from app.services.job_queue import JobQueueService
from app.rules.policy import AutomationPolicyLoader, PortalsPolicyEngine, PolicyDecision
from app.rules.loader import RuleLoader
from app.utils.logging import configure_logging

gifts_app = typer.Typer(help="Gift management commands")
console = Console()
GIFT_EXPORT_FIELDS = [
    "id",
    "telegram_gift_id",
    "owner_peer",
    "msg_id",
    "collectible_id",
    "slug",
    "title",
    "availability_issued",
    "availability_total",
    "is_for_sale",
    "resale_price_stars",
    "resale_price_ton",
    "transferred_to",
    "transferred_at",
    "first_seen_at",
    "updated_at",
]


def _effective_dry_run(cli_dry_run: bool, settings) -> bool:
    return cli_dry_run or settings.dry_run


def _ensure_price_allowed(settings, price_ton: float | None) -> None:
    if price_ton is None:
        return
    if price_ton <= 0:
        typer.echo("price_ton must be greater than 0.")
        raise typer.Exit(1)
    if settings.max_price_ton is not None and price_ton > settings.max_price_ton:
        typer.echo(
            f"Refusing to list above MAX_PRICE_TON={settings.max_price_ton}. "
            "Adjust .env if this is intentional."
        )
        raise typer.Exit(1)
    if settings.require_ton_rate_for_sales and settings.ton_to_stars_rate is None:
        typer.echo(
            "Refusing real listing without TON_TO_STARS_RATE. "
            "Set it in .env or run with --dry-run for preview."
        )
        raise typer.Exit(1)


def _render_rule_preview(matched: list[tuple[Gift, Rule]]) -> None:
    table = Table(title=f"Rule Preview ({len(matched)} matched)")
    table.add_column("Gift ID", style="dim")
    table.add_column("Title")
    table.add_column("Issued")
    table.add_column("Total")
    table.add_column("Current")
    table.add_column("Rule")
    table.add_column("Action")
    table.add_column("Price TON", style="yellow")

    for gift, rule in matched:
        table.add_row(
            str(gift.id),
            gift.title or "-",
            str(gift.availability_issued or "-"),
            str(gift.availability_total or "-"),
            "for sale" if gift.is_for_sale else "not listed",
            rule.name,
            rule.action,
            f"{rule.price_ton:.4f}" if rule.price_ton is not None else "-",
        )
    console.print(table)


def _render_portals_plan(decisions: list[PolicyDecision], destination_peer: str) -> None:
    table = Table(title=f"Portals Plan ({len(decisions)} matched -> {destination_peer})")
    table.add_column("Gift ID", style="dim")
    table.add_column("Title")
    table.add_column("Total")
    table.add_column("Decision")
    table.add_column("Reason")

    for decision in decisions:
        gift = decision.gift
        table.add_row(
            str(gift.id),
            gift.title or "-",
            str(gift.availability_total or "-"),
            "auto-approved" if decision.auto_approved else "needs approval",
            decision.reason,
        )
    console.print(table)


async def _run_created_jobs(sf, tg, pricing, settings, job_ids: list[int], dry_run: bool) -> None:
    queue_svc = JobQueueService(sf, tg, pricing, settings, dry_run=dry_run)
    for job_id in job_ids:
        await queue_svc.enqueue(job_id)
    queue_svc.start()
    await queue_svc.join()
    await queue_svc.stop()


def _filter_gifts(
    gifts: list[Gift],
    *,
    for_sale: bool | None = None,
    title_contains: str | None = None,
    collectible_id: int | None = None,
    include_transferred: bool = False,
    owner_peer: str | None = None,
) -> list[Gift]:
    result = gifts
    if owner_peer is not None:
        result = [gift for gift in result if gift.owner_peer == owner_peer]
    if not include_transferred:
        result = [gift for gift in result if gift.transferred_at is None]
    if for_sale is not None:
        result = [gift for gift in result if gift.is_for_sale == for_sale]
    if title_contains:
        needle = title_contains.lower()
        result = [gift for gift in result if gift.title and needle in gift.title.lower()]
    if collectible_id is not None:
        result = [gift for gift in result if gift.collectible_id == collectible_id]
    return result


def _gift_to_dict(gift: Gift) -> dict:
    return {
        "id": gift.id,
        "telegram_gift_id": gift.telegram_gift_id,
        "owner_peer": gift.owner_peer,
        "msg_id": gift.msg_id,
        "collectible_id": gift.collectible_id,
        "slug": gift.slug,
        "title": gift.title,
        "availability_issued": gift.availability_issued,
        "availability_total": gift.availability_total,
        "is_for_sale": gift.is_for_sale,
        "resale_price_stars": gift.resale_price_stars,
        "resale_price_ton": gift.resale_price_ton,
        "transferred_to": gift.transferred_to,
        "transferred_at": gift.transferred_at.isoformat() if gift.transferred_at else None,
        "first_seen_at": gift.first_seen_at.isoformat() if gift.first_seen_at else None,
        "updated_at": gift.updated_at.isoformat() if gift.updated_at else None,
    }


def _resolve_portals_recipient(settings, recipient: str | None) -> str:
    resolved = recipient or settings.portals_recipient
    if not resolved:
        typer.echo("Portals recipient is required. Pass --to or set PORTALS_RECIPIENT in .env.")
        raise typer.Exit(1)
    return resolved


# ---------------------------------------------------------------------------
# gifts scan
# ---------------------------------------------------------------------------

@gifts_app.command("scan")
def scan(
    dry_run: bool = typer.Option(False, "--dry-run", help="Do not modify DB"),
    peer: str | None = typer.Option(
        None,
        "--peer",
        help="Scan visible gifts owned by another profile using the current session",
    ),
) -> None:
    """Fetch all collectible gifts from Telegram and save them locally."""
    asyncio.run(_scan(dry_run, peer))


async def _scan(dry_run: bool, peer: str | None) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    async with TelegramClientContext(settings) as tg:
        if not await tg.raw.is_user_authorized():
            typer.echo("Not authenticated. Run: gifts-sales auth login")
            raise typer.Exit(1)

        owner_peer = peer or "self"
        input_peer = await tg.resolve_input_peer(peer) if peer else None

        sf = get_session_factory()
        async with sf() as session:
            gift_repo = GiftRepository(session)
            pricing = PricingService(tg, settings)
            svc = InventoryService(tg, gift_repo, pricing, settings)

            if dry_run:
                raw = await tg.get_saved_star_gifts(peer=input_peer)
                typer.echo(f"[dry-run] Would scan {len(raw)} gifts for owner_peer={owner_peer}.")
                return

            gifts = await svc.scan(owner_peer=owner_peer, peer=input_peer)
            await session.commit()

    typer.echo(f"Scanned and saved {len(gifts)} gifts for owner_peer={owner_peer}.")


# ---------------------------------------------------------------------------
# gifts list-local
# ---------------------------------------------------------------------------

@gifts_app.command("list-local")
def list_local(
    for_sale: bool | None = typer.Option(
        None,
        "--for-sale/--not-for-sale",
        help="Filter by current sale status",
    ),
    title_contains: str | None = typer.Option(None, "--title-contains", help="Filter by title"),
    collectible_id: int | None = typer.Option(None, "--collectible-id", help="Filter by collectible ID"),
    owner_peer: str | None = typer.Option(None, "--owner-peer", help="Filter by owner peer"),
    include_transferred: bool = typer.Option(
        False,
        "--include-transferred",
        help="Include gifts already transferred out",
    ),
) -> None:
    """Show all locally stored gifts."""
    asyncio.run(_list_local(for_sale, title_contains, collectible_id, owner_peer, include_transferred))


async def _list_local(
    for_sale: bool | None,
    title_contains: str | None,
    collectible_id: int | None,
    owner_peer: str | None,
    include_transferred: bool,
) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    sf = get_session_factory()
    async with sf() as session:
        gifts = await GiftRepository(session).list_all()
    gifts = _filter_gifts(
        gifts,
        for_sale=for_sale,
        title_contains=title_contains,
        collectible_id=collectible_id,
        owner_peer=owner_peer,
        include_transferred=include_transferred,
    )

    table = Table(title=f"Local Gifts ({len(gifts)})")
    table.add_column("ID", style="dim")
    table.add_column("Owner")
    table.add_column("TG Gift ID")
    table.add_column("Title")
    table.add_column("Issued")
    table.add_column("Total")
    table.add_column("For Sale", style="green")
    table.add_column("Price TON", style="yellow")
    table.add_column("Transferred")

    for g in gifts:
        table.add_row(
            str(g.id),
            g.owner_peer,
            g.telegram_gift_id,
            g.title or "-",
            str(g.availability_issued or "-"),
            str(g.availability_total or "-"),
            "yes" if g.is_for_sale else "no",
            f"{g.resale_price_ton:.4f}" if g.resale_price_ton else "-",
            g.transferred_to or "-",
        )
    console.print(table)


# ---------------------------------------------------------------------------
# gifts export
# ---------------------------------------------------------------------------

@gifts_app.command("export")
def export_gifts(
    output: Path = typer.Option(..., "--output", "-o", help="Output path (.csv or .json)"),
    format: str = typer.Option("csv", "--format", help="csv or json"),
    for_sale: bool | None = typer.Option(
        None,
        "--for-sale/--not-for-sale",
        help="Filter by current sale status",
    ),
    title_contains: str | None = typer.Option(None, "--title-contains", help="Filter by title"),
    collectible_id: int | None = typer.Option(None, "--collectible-id", help="Filter by collectible ID"),
    owner_peer: str | None = typer.Option(None, "--owner-peer", help="Filter by owner peer"),
    include_transferred: bool = typer.Option(
        False,
        "--include-transferred",
        help="Include gifts already transferred out",
    ),
) -> None:
    """Export locally stored gifts for analysis."""
    asyncio.run(
        _export_gifts(
            output,
            format,
            for_sale,
            title_contains,
            collectible_id,
            owner_peer,
            include_transferred,
        )
    )


async def _export_gifts(
    output: Path,
    format: str,
    for_sale: bool | None,
    title_contains: str | None,
    collectible_id: int | None,
    owner_peer: str | None,
    include_transferred: bool,
) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    normalized_format = format.lower()
    if normalized_format not in {"csv", "json"}:
        typer.echo("Unknown format. Valid: csv, json")
        raise typer.Exit(1)

    sf = get_session_factory()
    async with sf() as session:
        gifts = await GiftRepository(session).list_all()
    gifts = _filter_gifts(
        gifts,
        for_sale=for_sale,
        title_contains=title_contains,
        collectible_id=collectible_id,
        owner_peer=owner_peer,
        include_transferred=include_transferred,
    )
    rows = [_gift_to_dict(gift) for gift in gifts]

    output.parent.mkdir(parents=True, exist_ok=True)
    if normalized_format == "json":
        output.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        with output.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=GIFT_EXPORT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    typer.echo(f"Exported {len(gifts)} gift(s) to {output}.")


# ---------------------------------------------------------------------------
# gifts show
# ---------------------------------------------------------------------------

@gifts_app.command("show")
def show(
    gift_id: int = typer.Option(..., "--gift-id", help="Local gift ID"),
) -> None:
    """Show full details for a gift."""
    asyncio.run(_show(gift_id))


async def _show(gift_id: int) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    sf = get_session_factory()
    async with sf() as session:
        gift = await GiftRepository(session).get_by_id(gift_id)

    if gift is None:
        typer.echo(f"Gift {gift_id} not found. Run 'gifts scan' first.")
        raise typer.Exit(1)

    data = {
        "id": gift.id,
        "telegram_gift_id": gift.telegram_gift_id,
        "owner_peer": gift.owner_peer,
        "msg_id": gift.msg_id,
        "collectible_id": gift.collectible_id,
        "slug": gift.slug,
        "title": gift.title,
        "availability_issued": gift.availability_issued,
        "availability_total": gift.availability_total,
        "is_for_sale": gift.is_for_sale,
        "resale_price_stars": gift.resale_price_stars,
        "resale_price_ton": gift.resale_price_ton,
        "transferred_to": gift.transferred_to,
        "transferred_at": gift.transferred_at.isoformat() if gift.transferred_at else None,
        "first_seen_at": gift.first_seen_at.isoformat() if gift.first_seen_at else None,
        "updated_at": gift.updated_at.isoformat() if gift.updated_at else None,
    }
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# gifts list (sell)
# ---------------------------------------------------------------------------

@gifts_app.command("list")
def list_gift(
    gift_id: int = typer.Option(..., "--gift-id", help="Local gift ID"),
    price_ton: float = typer.Option(..., "--price-ton", help="Listing price in TON"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip Telegram call"),
) -> None:
    """List a gift for sale on the marketplace."""
    asyncio.run(_list_gift(gift_id, price_ton, dry_run))


async def _list_gift(gift_id: int, price_ton: float, dry_run: bool) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)
    effective_dry_run = _effective_dry_run(dry_run, settings)
    if price_ton <= 0:
        typer.echo("price_ton must be greater than 0.")
        raise typer.Exit(1)
    if not effective_dry_run:
        _ensure_price_allowed(settings, price_ton)

    sf = get_session_factory()

    if effective_dry_run:
        async with sf() as session:
            gift_repo = GiftRepository(session)
            gift = await gift_repo.get_by_id(gift_id)
            if gift is None:
                typer.echo(f"Gift {gift_id} not found.")
                raise typer.Exit(1)
            pricing = PricingService(None, settings)
            listing = ListingService(None, gift_repo, pricing, settings)
            await listing.list_gift(gift, price_ton, dry_run=True)
        typer.echo(f"[dry-run] Would list gift {gift_id} at {price_ton} TON.")
        return

    async with TelegramClientContext(settings) as tg:
        if not await tg.raw.is_user_authorized():
            typer.echo("Not authenticated.")
            raise typer.Exit(1)

        pricing = PricingService(tg, settings)
        async with sf() as session:
            gift_repo = GiftRepository(session)
            job_repo = JobRepository(session)
            gift = await gift_repo.get_by_id(gift_id)

            if gift is None:
                typer.echo(f"Gift {gift_id} not found.")
                raise typer.Exit(1)

            job_schema = JobCreateSchema(
                job_type=JobType.LIST,
                gift_id=gift.id,
                telegram_gift_id=gift.telegram_gift_id,
                price_ton=price_ton,
                max_attempts=settings.max_job_attempts,
            )
            job, created = await job_repo.create_if_not_exists(job_schema)

            if not created and job.status not in (JobStatus.FAILED, JobStatus.SKIPPED):
                typer.echo(
                    f"Job already exists (id={job.id}, status={job.status.value}). "
                    "Use 'jobs retry' to force."
                )
                raise typer.Exit(0)

            job_id = job.id
            await session.commit()

        await _run_created_jobs(sf, tg, pricing, settings, [job_id], dry_run=False)

    action = "Listed"
    typer.echo(f"{action} gift {gift_id} at {price_ton} TON.")


# ---------------------------------------------------------------------------
# gifts delist
# ---------------------------------------------------------------------------

@gifts_app.command("delist")
def delist_gift(
    gift_id: int = typer.Option(..., "--gift-id", help="Local gift ID"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip Telegram call"),
) -> None:
    """Remove a gift from sale."""
    asyncio.run(_delist_gift(gift_id, dry_run))


async def _delist_gift(gift_id: int, dry_run: bool) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)
    effective_dry_run = _effective_dry_run(dry_run, settings)

    sf = get_session_factory()
    if effective_dry_run:
        async with sf() as session:
            gift_repo = GiftRepository(session)
            gift = await gift_repo.get_by_id(gift_id)
            if gift is None:
                typer.echo(f"Gift {gift_id} not found.")
                raise typer.Exit(1)
            pricing = PricingService(None, settings)
            listing = ListingService(None, gift_repo, pricing, settings)
            await listing.delist_gift(gift, dry_run=True)
        typer.echo(f"[dry-run] Would delist gift {gift_id}.")
        return

    async with TelegramClientContext(settings) as tg:
        if not await tg.raw.is_user_authorized():
            typer.echo("Not authenticated.")
            raise typer.Exit(1)

        pricing = PricingService(tg, settings)
        async with sf() as session:
            gift_repo = GiftRepository(session)
            job_repo = JobRepository(session)
            gift = await gift_repo.get_by_id(gift_id)

            if gift is None:
                typer.echo(f"Gift {gift_id} not found.")
                raise typer.Exit(1)

            job_schema = JobCreateSchema(
                job_type=JobType.DELIST,
                gift_id=gift.id,
                telegram_gift_id=gift.telegram_gift_id,
                max_attempts=settings.max_job_attempts,
            )
            job, created = await job_repo.create_if_not_exists(job_schema)

            if not created and job.status not in (JobStatus.FAILED, JobStatus.SKIPPED):
                typer.echo(f"Delist job already exists (id={job.id}, status={job.status.value}).")
                raise typer.Exit(0)

            job_id = job.id
            await session.commit()

        await _run_created_jobs(sf, tg, pricing, settings, [job_id], dry_run=False)

    action = "Delisted"
    typer.echo(f"{action} gift {gift_id}.")


# ---------------------------------------------------------------------------
# gifts transfer / send-to-portals
# ---------------------------------------------------------------------------

@gifts_app.command("transfer")
def transfer_gift(
    gift_id: int = typer.Option(..., "--gift-id", help="Local gift ID"),
    to: str = typer.Option(..., "--to", help="Destination username, channel, bot, or ID"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without Telegram call"),
) -> None:
    """Transfer a collectible gift to another Telegram peer."""
    asyncio.run(_transfer_gift(gift_id, to, dry_run))


@gifts_app.command("send-to-portals")
def send_to_portals(
    gift_id: int = typer.Option(..., "--gift-id", help="Local gift ID"),
    to: str | None = typer.Option(
        None,
        "--to",
        help="Portals recipient override; defaults to PORTALS_RECIPIENT",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without Telegram call"),
) -> None:
    """Transfer a collectible gift to the configured Portals recipient."""
    settings = get_settings()
    recipient = _resolve_portals_recipient(settings, to)
    asyncio.run(_transfer_gift(gift_id, recipient, dry_run))


async def _transfer_gift(gift_id: int, destination_peer: str, dry_run: bool) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)
    effective_dry_run = _effective_dry_run(dry_run, settings)

    sf = get_session_factory()
    if effective_dry_run:
        async with sf() as session:
            gift_repo = GiftRepository(session)
            gift = await gift_repo.get_by_id(gift_id)
            if gift is None:
                typer.echo(f"Gift {gift_id} not found.")
                raise typer.Exit(1)
            transfer = TransferService(None, gift_repo, settings)
            await transfer.transfer_gift(gift, destination_peer, dry_run=True)
        typer.echo(f"[dry-run] Would transfer gift {gift_id} to {destination_peer}.")
        return

    async with TelegramClientContext(settings) as tg:
        if not await tg.raw.is_user_authorized():
            typer.echo("Not authenticated.")
            raise typer.Exit(1)

        pricing = PricingService(tg, settings)
        async with sf() as session:
            gift_repo = GiftRepository(session)
            job_repo = JobRepository(session)
            gift = await gift_repo.get_by_id(gift_id)

            if gift is None:
                typer.echo(f"Gift {gift_id} not found.")
                raise typer.Exit(1)
            if gift.transferred_at is not None:
                typer.echo(f"Gift {gift_id} was already transferred to {gift.transferred_to}.")
                raise typer.Exit(0)

            schema = JobCreateSchema(
                job_type=JobType.TRANSFER,
                gift_id=gift.id,
                telegram_gift_id=gift.telegram_gift_id,
                destination_peer=destination_peer,
                max_attempts=settings.max_job_attempts,
            )
            job, created = await job_repo.create_if_not_exists(schema)

            if not created and job.status not in (JobStatus.FAILED, JobStatus.SKIPPED):
                typer.echo(
                    f"Transfer job already exists (id={job.id}, status={job.status.value}). "
                    "Use 'jobs retry' to force."
                )
                raise typer.Exit(0)

            job_id = job.id
            await session.commit()

        await _run_created_jobs(sf, tg, pricing, settings, [job_id], dry_run=False)

    typer.echo(f"Transferred gift {gift_id} to {destination_peer}.")


# ---------------------------------------------------------------------------
# gifts plan-portals
# ---------------------------------------------------------------------------

@gifts_app.command("plan-portals")
def plan_portals(
    policy_file: Path = typer.Option(
        Path("rules/portals_policy.yaml"),
        "--policy-file",
        help="Automation policy YAML",
    ),
    to: str | None = typer.Option(
        None,
        "--to",
        help="Portals recipient override; defaults to policy recipient or PORTALS_RECIPIENT",
    ),
    create_approvals: bool = typer.Option(
        False,
        "--create-approvals",
        help="Persist approval requests from this plan",
    ),
) -> None:
    """Plan Portals transfers from local gifts using an automation policy."""
    asyncio.run(_plan_portals(policy_file, to, create_approvals))


async def _plan_portals(policy_file: Path, to: str | None, create_approvals: bool) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    policy = AutomationPolicyLoader.load(policy_file).portals
    destination_peer = to or policy.recipient or settings.portals_recipient
    if not destination_peer:
        typer.echo("Portals recipient is required. Pass --to, set policy recipient, or set PORTALS_RECIPIENT.")
        raise typer.Exit(1)

    sf = get_session_factory()
    async with sf() as session:
        gifts = await GiftRepository(session).list_all(owner_peer=policy.match.owner_peer)
        decisions = PortalsPolicyEngine.plan(gifts, policy)
        _render_portals_plan(decisions, destination_peer)

        if not create_approvals:
            typer.echo("[preview] No approval requests created. Use --create-approvals to persist.")
            return

        repo = ApprovalRepository(session)
        notifier = ApprovalNotifier(settings.bot_token, settings.approval_chat_id)
        created = 0
        skipped = 0
        auto_approved = 0
        notified = 0
        for decision in decisions:
            status = (
                ApprovalStatus.APPROVED
                if decision.auto_approved
                else ApprovalStatus.PENDING
            )
            approval, was_created = await repo.create_if_not_exists(
                ApprovalCreateSchema(
                    action=ApprovalAction.TRANSFER_PORTALS,
                    gift_id=decision.gift.id,
                    destination_peer=destination_peer,
                    reason=decision.reason,
                    policy_name=policy.name,
                    status=status,
                )
            )
            if was_created:
                created += 1
                if approval.status == ApprovalStatus.APPROVED:
                    auto_approved += 1
                elif notifier.send_approval_request(approval):
                    notified += 1
            else:
                skipped += 1
        await session.commit()

    typer.echo(
        f"Approvals created: {created}, skipped: {skipped}, "
        f"auto-approved: {auto_approved}, notified: {notified}."
    )


# ---------------------------------------------------------------------------
# gifts bulk-list
# ---------------------------------------------------------------------------

@gifts_app.command("bulk-list")
def bulk_list(
    rule_file: Path = typer.Option(..., "--rule-file", help="Path to YAML rule file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip Telegram calls"),
) -> None:
    """List/delist gifts in bulk according to YAML rules."""
    asyncio.run(_bulk_list(rule_file, dry_run))


async def _bulk_list(rule_file: Path, dry_run: bool) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)
    effective_dry_run = _effective_dry_run(dry_run, settings)

    rule_set = RuleLoader.load(rule_file)
    typer.echo(f"Loaded {len(rule_set.rules)} rules from {rule_file}.")

    sf = get_session_factory()
    async with sf() as session:
        gift_repo = GiftRepository(session)
        gifts = await gift_repo.list_all()

    matched = RuleLoader.apply_rules(gifts, rule_set)
    typer.echo(f"Matched {len(matched)} gifts.")
    _render_rule_preview(matched)

    executable = [(gift, rule) for gift, rule in matched if not rule.dry_run]
    if effective_dry_run:
        typer.echo("[dry-run] Preview only. No jobs created and no Telegram calls made.")
        return

    if len(executable) > settings.max_bulk_jobs:
        typer.echo(
            f"Refusing to create {len(executable)} jobs; MAX_BULK_JOBS={settings.max_bulk_jobs}. "
            "Raise the limit in .env if this is intentional."
        )
        raise typer.Exit(1)

    for _, rule in executable:
        if rule.action == "list":
            _ensure_price_allowed(settings, rule.price_ton)

    skipped_rule_dry_runs = len(matched) - len(executable)
    if skipped_rule_dry_runs:
        typer.echo(f"Skipping {skipped_rule_dry_runs} rule-level dry-run match(es).")

    if not executable:
        typer.echo("No executable matches.")
        return

    async with TelegramClientContext(settings) as tg:
        if not await tg.raw.is_user_authorized():
            typer.echo("Not authenticated.")
            raise typer.Exit(1)

        pricing = PricingService(tg, settings)
        jobs_created = 0
        jobs_skipped = 0
        job_ids: list[int] = []

        async with sf() as session:
            job_repo = JobRepository(session)

            for gift, rule in executable:
                job_type = JobType.LIST if rule.action == "list" else JobType.DELIST
                price = rule.price_ton if rule.action == "list" else None
                schema = JobCreateSchema(
                    job_type=job_type,
                    gift_id=gift.id,
                    telegram_gift_id=gift.telegram_gift_id,
                    price_ton=price,
                    max_attempts=rule.max_attempts,
                )
                job, created = await job_repo.create_if_not_exists(schema)
                if created:
                    jobs_created += 1
                    job_ids.append(job.id)
                else:
                    jobs_skipped += 1

            await session.commit()

        typer.echo(f"Jobs created: {jobs_created}, skipped (already exist): {jobs_skipped}.")

        if job_ids:
            typer.echo("Processing jobs...")
            await _run_created_jobs(sf, tg, pricing, settings, job_ids, dry_run=False)
            typer.echo("Done.")
