import typer

from app.cli.auth import auth_app
from app.cli.approvals import approvals_app
from app.cli.gifts import gifts_app
from app.cli.jobs import jobs_app
from app.cli.markets import markets_app

app = typer.Typer(
    name="gifts-sales",
    help="Telegram collectible gifts marketplace userbot",
    no_args_is_help=True,
)

app.add_typer(auth_app, name="auth")
app.add_typer(approvals_app, name="approvals")
app.add_typer(gifts_app, name="gifts")
app.add_typer(jobs_app, name="jobs")
app.add_typer(markets_app, name="markets")


if __name__ == "__main__":
    app()
