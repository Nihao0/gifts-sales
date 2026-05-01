import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.client.telegram import TelegramClientContext
from app.config.settings import get_settings
from app.models.approval import ApprovalAction, ApprovalStatus
from app.models.job import JobType
from app.schemas.job import JobCreateSchema
from app.services.job_queue import JobQueueService
from app.services.pricing import PricingService
from app.storage.approval_repo import ApprovalRepository
from app.storage.database import get_session_factory, init_db
from app.storage.job_repo import JobRepository
from app.utils.logging import configure_logging

approvals_app = typer.Typer(help="Approval request management")
console = Console()


@approvals_app.command("list")
def list_approvals(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
) -> None:
    """List approval requests."""
    asyncio.run(_list_approvals(status))


async def _list_approvals(status_str: str | None) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    status: ApprovalStatus | None = None
    if status_str:
        try:
            status = ApprovalStatus(status_str)
        except ValueError:
            typer.echo("Unknown status. Valid: pending, approved, rejected, executed")
            raise typer.Exit(1)

    sf = get_session_factory()
    async with sf() as session:
        approvals = await ApprovalRepository(session).get_all(status)

    table = Table(title=f"Approvals ({len(approvals)})")
    table.add_column("ID", style="dim")
    table.add_column("Action")
    table.add_column("Gift ID")
    table.add_column("Gift")
    table.add_column("Status")
    table.add_column("Destination")
    table.add_column("Policy")
    table.add_column("Reason")

    for approval in approvals:
        table.add_row(
            str(approval.id),
            approval.action.value,
            str(approval.gift_id),
            approval.gift.title or "-",
            approval.status.value,
            approval.destination_peer,
            approval.policy_name or "-",
            approval.reason or "-",
        )
    console.print(table)


@approvals_app.command("approve")
def approve(
    approval_id: int = typer.Option(..., "--id", help="Approval request ID"),
) -> None:
    """Approve a request."""
    asyncio.run(_approve(approval_id))


async def _approve(approval_id: int) -> None:
    await _set_approval_status(approval_id, ApprovalStatus.APPROVED)
    typer.echo(f"Approved request {approval_id}.")


@approvals_app.command("reject")
def reject(
    approval_id: int = typer.Option(..., "--id", help="Approval request ID"),
) -> None:
    """Reject a request."""
    asyncio.run(_reject(approval_id))


async def _reject(approval_id: int) -> None:
    await _set_approval_status(approval_id, ApprovalStatus.REJECTED)
    typer.echo(f"Rejected request {approval_id}.")


async def _set_approval_status(approval_id: int, status: ApprovalStatus) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    sf = get_session_factory()
    async with sf() as session:
        repo = ApprovalRepository(session)
        approval = await repo.get_by_id(approval_id)
        if approval is None:
            typer.echo(f"Approval request {approval_id} not found.")
            raise typer.Exit(1)
        if status == ApprovalStatus.APPROVED:
            await repo.approve(approval_id)
        else:
            await repo.reject(approval_id)
        await session.commit()


@approvals_app.command("run-approved")
def run_approved() -> None:
    """Create jobs for approved requests and process them."""
    asyncio.run(_run_approved())


async def _run_approved() -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    sf = get_session_factory()
    async with TelegramClientContext(settings) as tg:
        if not await tg.raw.is_user_authorized():
            typer.echo("Not authenticated.")
            raise typer.Exit(1)

        pricing = PricingService(tg, settings)
        job_ids: list[int] = []
        async with sf() as session:
            approval_repo = ApprovalRepository(session)
            job_repo = JobRepository(session)
            approvals = await approval_repo.get_approved_for_execution()

            for approval in approvals:
                if approval.action != ApprovalAction.TRANSFER_PORTALS:
                    continue
                if approval.gift.owner_peer != "self":
                    typer.echo(f"Skipping approval {approval.id}: gift is not owned by self.")
                    continue

                job, _ = await job_repo.create_if_not_exists(
                    JobCreateSchema(
                        job_type=JobType.TRANSFER,
                        gift_id=approval.gift_id,
                        telegram_gift_id=approval.gift.telegram_gift_id,
                        destination_peer=approval.destination_peer,
                        max_attempts=settings.max_job_attempts,
                    )
                )
                await approval_repo.mark_executed(approval.id, job.id)
                job_ids.append(job.id)

            await session.commit()

        if not job_ids:
            typer.echo("No approved requests to run.")
            return

        queue = JobQueueService(sf, tg, pricing, settings)
        for job_id in job_ids:
            await queue.enqueue(job_id)
        typer.echo(f"Processing {len(job_ids)} approved job(s)...")
        queue.start()
        await queue.join()
        await queue.stop()
        typer.echo("Done.")
