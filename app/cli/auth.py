import asyncio

import typer

from app.config.settings import get_settings
from app.client.telegram import TelegramClientContext
from app.utils.logging import configure_logging, get_logger

auth_app = typer.Typer(help="Authentication commands")
log = get_logger(__name__)


@auth_app.command("login")
def login(
    phone: str = typer.Option(None, "--phone", "-p", help="Phone (overrides .env)"),
    password: str = typer.Option(None, "--password", help="2FA password"),
) -> None:
    """Authenticate and save a Telethon session."""
    asyncio.run(_login(phone, password))


@auth_app.command("whoami")
def whoami() -> None:
    """Show the currently authenticated Telegram user."""
    asyncio.run(_whoami())


async def _login(phone: str | None, password: str | None) -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    async with TelegramClientContext(settings) as tg:
        await tg.start(phone=phone, password=password)
        me = await tg.get_me()
    typer.echo(f"Logged in as: {me.first_name} (@{me.username}) id={me.id}")


async def _whoami() -> None:
    settings = get_settings()
    settings.ensure_data_dir()
    configure_logging(settings.log_level, settings.log_format)
    async with TelegramClientContext(settings) as tg:
        if not await tg.raw.is_user_authorized():
            typer.echo("Not authenticated. Run: gifts-sales auth login")
            raise typer.Exit(1)
        me = await tg.get_me()
    typer.echo(f"User: {me.first_name} (@{me.username}) id={me.id} phone={me.phone}")
