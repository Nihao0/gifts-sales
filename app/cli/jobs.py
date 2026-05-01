import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from app.client.telegram import TelegramClientContext
from app.config.settings import get_settings
from app.models.job import JobStatus
from app.storage.database import get_session_factory, init_db
from app.storage.job_repo import JobRepository
from app.services.job_queue import JobQueueService
from app.services.pricing import PricingService
from app.utils.logging import configure_logging

jobs_app = typer.Typer(help="Job queue management")
console = Console()


@jobs_app.command("list")
def list_jobs(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
) -> None:
    """List all jobs (optionally filtered by status)."""
    asyncio.run(_list_jobs(status))


async def _list_jobs(status_str: str | None) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    status: JobStatus | None = None
    if status_str:
        try:
            status = JobStatus(status_str)
        except ValueError:
            typer.echo(f"Unknown status: {status_str}. Valid: pending, running, done, failed, skipped")
            raise typer.Exit(1)

    sf = get_session_factory()
    async with sf() as session:
        jobs = await JobRepository(session).get_all(status)

    table = Table(title=f"Jobs ({len(jobs)})")
    table.add_column("ID", style="dim")
    table.add_column("Type")
    table.add_column("Gift ID")
    table.add_column("Status")
    table.add_column("Price TON")
    table.add_column("Destination")
    table.add_column("Attempts")
    table.add_column("Retry After")
    table.add_column("Error")

    for j in jobs:
        table.add_row(
            str(j.id),
            j.job_type.value,
            str(j.gift_id),
            j.status.value,
            f"{j.price_ton:.4f}" if j.price_ton else "-",
            j.destination_peer or "-",
            f"{j.attempts}/{j.max_attempts}",
            str(j.retry_after) if j.retry_after else "-",
            (j.error_info or "")[:60],
        )
    console.print(table)


@jobs_app.command("retry")
def retry_job(
    job_id: int = typer.Option(..., "--job-id", help="Job ID to retry"),
) -> None:
    """Reset a specific job to PENDING for retry."""
    asyncio.run(_retry_job(job_id))


async def _retry_job(job_id: int) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    sf = get_session_factory()
    async with sf() as session:
        repo = JobRepository(session)
        job = await repo.get_by_id(job_id)
        if job is None:
            typer.echo(f"Job {job_id} not found.")
            raise typer.Exit(1)
        await repo.reset_for_retry(job_id)
        await session.commit()

    typer.echo(f"Job {job_id} reset to PENDING.")


@jobs_app.command("retry-failed")
def retry_failed() -> None:
    """Reset all FAILED jobs to PENDING."""
    asyncio.run(_retry_failed())


async def _retry_failed() -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    await init_db(settings.db_url)

    sf = get_session_factory()
    async with sf() as session:
        repo = JobRepository(session)
        failed = await repo.get_failed()
        for job in failed:
            await repo.reset_for_retry(job.id)
        await session.commit()

    typer.echo(f"Reset {len(failed)} failed job(s) to PENDING.")


@jobs_app.command("run")
def run_jobs() -> None:
    """Run all pending jobs that are due now."""
    asyncio.run(_run_jobs())


async def _run_jobs() -> None:
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
        queue = JobQueueService(sf, tg, pricing, settings)
        count = await queue.enqueue_pending_from_db()
        if count == 0:
            typer.echo("No pending jobs are due.")
            return

        typer.echo(f"Processing {count} pending job(s)...")
        queue.start()
        await queue.join()
        await queue.stop()
        typer.echo("Done.")
