from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from pathlib import Path
from typing import Annotated

import typer

from glean import __version__
from glean.config import Config, load_config
from glean.config.loader import ConfigError
from glean.logging import configure_logging, get_logger

app = typer.Typer(
    add_completion=False,
    help="glean — pluggable feed digester for Telegram.",
    no_args_is_help=True,
)

logger = get_logger("cli")

_DEFAULT_CONFIG = "/etc/glean/feeds.yaml"
_DEFAULT_DB = "/data/state.db"

ConfigOpt = Annotated[
    Path,
    typer.Option(
        "--config",
        "-c",
        envvar="GLEAN_CONFIG",
        help="Path to feeds.yaml",
    ),
]
DbOpt = Annotated[
    Path,
    typer.Option(
        "--db",
        envvar="GLEAN_DB",
        help="Path to SQLite state DB",
    ),
]
LogLevelOpt = Annotated[
    str,
    typer.Option("--log-level", envvar="LOG_LEVEL"),
]


def _load_or_exit(path: Path) -> Config:
    try:
        return load_config(path)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None


def _require_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        typer.secho("TELEGRAM_BOT_TOKEN is not set", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    return token


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(f"glean {__version__}")


@app.command("validate-config")
def validate_config(
    config: ConfigOpt = Path(_DEFAULT_CONFIG),
    log_level: LogLevelOpt = "WARNING",
) -> None:
    """Parse feeds.yaml and exit 0 if valid, 1 otherwise."""
    configure_logging(log_level)
    cfg = _load_or_exit(config)
    typer.echo(f"OK — {len(cfg.feeds)} feed(s)")
    for feed in cfg.feeds:
        typer.echo(f"  - {feed.name}: schedule={feed.schedule!r} sources={len(feed.sources)}")


@app.command("list-feeds")
def list_feeds(
    config: ConfigOpt = Path(_DEFAULT_CONFIG),
    db: DbOpt = Path(_DEFAULT_DB),
    log_level: LogLevelOpt = "WARNING",
) -> None:
    """Show configured feeds and their last-run state."""
    configure_logging(log_level)
    cfg = _load_or_exit(config)
    asyncio.run(_list_feeds_async(cfg, db))


async def _list_feeds_async(cfg, db_path: Path) -> None:  # type: ignore[no-untyped-def]
    from glean.state.store import StateStore

    store = StateStore(db_path)
    await store.open()
    try:
        for feed in cfg.feeds:
            async with store.db.execute(
                "SELECT last_success_at, last_error, consecutive_failures, "
                "alert_active, bootstrapped FROM feed_runs WHERE feed = ?",
                (feed.name,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                state_str = "never run"
            else:
                ls, le, cf, alert, boot = row
                bits = []
                if ls:
                    import datetime as dt

                    bits.append(f"last_ok={dt.datetime.fromtimestamp(ls).isoformat()}")
                if cf:
                    bits.append(f"failures={cf}")
                if alert:
                    bits.append("ALERTING")
                if not boot:
                    bits.append("pre-bootstrap")
                state_str = ", ".join(bits) or "ok"
            llm = feed.effective_llm(cfg.defaults)
            typer.echo(
                f"{feed.name:20s}  schedule={feed.schedule!r:18s}  "
                f"llm={llm.provider}:{llm.model:18s}  {state_str}"
            )
            if row and row[1]:
                typer.echo(f"  last_error: {row[1]}")
    finally:
        await store.close()


@app.command("test-feed")
def test_feed(
    name: str,
    config: ConfigOpt = Path(_DEFAULT_CONFIG),
    db: DbOpt = Path(_DEFAULT_DB),
    send: Annotated[bool, typer.Option("--send", help="Actually send to Telegram.")] = False,
    log_level: LogLevelOpt = "INFO",
) -> None:
    """Run a feed once. Default is dry-run (no Telegram, no state writes)."""
    configure_logging(log_level)
    cfg = _load_or_exit(config)
    try:
        cfg.feed(name)
    except KeyError:
        typer.secho(f"no such feed: {name}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    asyncio.run(_test_feed_async(cfg, db, name, send=send))


async def _test_feed_async(cfg, db_path: Path, name: str, *, send: bool) -> None:  # type: ignore[no-untyped-def]
    from glean.pipeline.engine import Runner
    from glean.state.store import StateStore
    from glean.telegram import TelegramSender

    store = StateStore(db_path)
    await store.open()
    telegram = TelegramSender(_require_token()) if send else None
    runner = Runner(cfg, store, telegram)
    try:
        result = await runner.run_feed(name, dry_run=not send)
        typer.echo("---")
        typer.echo(
            f"feed={result.feed} fetched={result.fetched} "
            f"after_dedup={result.after_dedup} dropped={result.dropped} "
            f"overflow={result.overflow} sent={result.sent} "
            f"duration_ms={result.duration_ms}"
        )
        if result.skipped_reason:
            typer.echo(f"skipped: {result.skipped_reason}")
        if result.error:
            typer.secho(f"error: {result.error}", fg=typer.colors.RED)
            raise typer.Exit(code=2)
        if result.messages and not send:
            typer.echo("---  WOULD SEND  ---")
            for i, msg in enumerate(result.messages, 1):
                typer.echo(f"\n[message {i}]\n{msg}")
    finally:
        await runner.aclose()
        await store.close()


@app.command("send-now")
def send_now(
    name: str,
    config: ConfigOpt = Path(_DEFAULT_CONFIG),
    db: DbOpt = Path(_DEFAULT_DB),
    log_level: LogLevelOpt = "INFO",
) -> None:
    """Run a feed off-schedule and actually send to Telegram."""
    configure_logging(log_level)
    cfg = _load_or_exit(config)
    try:
        cfg.feed(name)
    except KeyError:
        typer.secho(f"no such feed: {name}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    asyncio.run(_test_feed_async(cfg, db, name, send=True))


@app.command()
def run(
    config: ConfigOpt = Path(_DEFAULT_CONFIG),
    db: DbOpt = Path(_DEFAULT_DB),
    health_port: Annotated[int, typer.Option(envvar="HEALTH_PORT")] = 9090,
    log_level: LogLevelOpt = "INFO",
) -> None:
    """Run the scheduler daemon."""
    configure_logging(log_level)
    cfg = _load_or_exit(config)
    asyncio.run(_run_async(cfg, db, health_port))


async def _run_async(cfg, db_path: Path, health_port: int) -> None:  # type: ignore[no-untyped-def]
    from apscheduler import AsyncScheduler

    from glean.health import run_health_server
    from glean.pipeline.engine import Runner
    from glean.scheduler import schedule_feeds
    from glean.state.store import StateStore
    from glean.telegram import TelegramSender

    store = StateStore(db_path)
    await store.open()
    telegram = TelegramSender(_require_token())
    runner = Runner(cfg, store, telegram)
    health_runner = await run_health_server(store, port=health_port)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop_event.set)

    try:
        async with AsyncScheduler() as scheduler:
            await schedule_feeds(scheduler, runner)
            await scheduler.start_in_background()
            logger.info("daemon_started", feeds=len(cfg.feeds))
            await stop_event.wait()
            logger.info("shutdown_requested")
    finally:
        await health_runner.cleanup()
        await runner.aclose()
        await store.close()


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
