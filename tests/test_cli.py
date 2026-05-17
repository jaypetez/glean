from __future__ import annotations

import importlib
import runpy
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from glean import __version__
from glean.config.schema import Config
from glean.state.store import StateStore

cli_module = importlib.import_module("glean.cli.app")

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")


@pytest.fixture(autouse=True)
def _stub_configure_logging(monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "configure_logging", lambda *args, **kwargs: None)


def _config_text() -> str:
    return textwrap.dedent(
        """
        defaults:
          llm:
            provider: ollama
            model: qwen2.5:7b
        feeds:
          - name: ai
            schedule: "every 1h"
            chat_id: -1001
            sources:
              - type: rss
                url: https://example.com/feed
            pipeline:
              - dedup
        """
    )


def _make_cfg(*names: str) -> Config:
    return Config.model_validate(
        {
            "defaults": {"llm": {"provider": "ollama", "model": "qwen2.5:7b"}},
            "feeds": [
                {
                    "name": name,
                    "schedule": "every 1h",
                    "chat_id": -1000 - index,
                    "sources": [{"type": "rss", "url": f"https://example.com/{name}"}],
                    "pipeline": ["dedup"],
                }
                for index, name in enumerate(names)
            ],
        }
    )


def test_version_command_prints_package_version() -> None:
    result = CliRunner().invoke(cli_module.app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"glean {__version__}"


def test_validate_config_command_reports_success(write_yaml) -> None:
    config_path = write_yaml(_config_text())

    result = CliRunner().invoke(cli_module.app, ["validate-config", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "OK — 1 feed(s)" in result.stdout
    assert "ai: schedule='every 1h' sources=1" in result.stdout


def test_validate_config_command_exits_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"

    result = CliRunner().invoke(cli_module.app, ["validate-config", "--config", str(missing)])

    assert result.exit_code == 1
    assert f"config file not found: {missing}" in result.output


def test_migrate_command_passes_db_to_async_runner(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    captured: dict[str, object] = {}

    async def fake_migrate(db: Path) -> None:
        captured["db"] = db

    monkeypatch.setattr(cli_module, "_migrate_async", fake_migrate, raising=False)

    result = CliRunner().invoke(cli_module.app, ["migrate", "--db", str(db_path)])

    assert result.exit_code == 0
    assert captured["db"] == db_path


def test_list_feeds_command_passes_loaded_config_to_async_runner(
    monkeypatch,
    write_yaml,
    tmp_path: Path,
) -> None:
    config_path = write_yaml(_config_text())
    db_path = tmp_path / "state.db"
    captured: dict[str, object] = {}

    async def fake_list_feeds(cfg: Config, db: Path) -> None:
        captured["cfg"] = cfg
        captured["db"] = db

    monkeypatch.setattr(cli_module, "_list_feeds_async", fake_list_feeds)

    result = CliRunner().invoke(
        cli_module.app,
        ["list-feeds", "--config", str(config_path), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert captured["db"] == db_path
    assert isinstance(captured["cfg"], Config)
    assert captured["cfg"].feeds[0].name == "ai"


@pytest.mark.asyncio
async def test_list_feeds_async_renders_state_information(
    capsys,
    tmp_path: Path,
) -> None:
    cfg = _make_cfg("ai", "ops")
    db_path = tmp_path / "state.db"
    store = StateStore(db_path)
    await store.open()
    try:
        await store.db.execute(
            """
            INSERT INTO feed_runs(
                feed, last_success_at, last_error, consecutive_failures, alert_active, bootstrapped
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("ai", 1710000000, "boom", 2, 1, 0),
        )
        await store.db.commit()
    finally:
        await store.close()

    await cli_module._list_feeds_async(cfg, db_path)

    output = capsys.readouterr().out
    assert "ai" in output
    assert "last_ok=" in output
    assert "failures=2" in output
    assert "ALERTING" in output
    assert "pre-bootstrap" in output
    assert "last_error: boom" in output
    assert "ops" in output


def test_test_feed_command_checks_feed_exists_before_running(
    monkeypatch,
    write_yaml,
    tmp_path: Path,
) -> None:
    config_path = write_yaml(_config_text())
    db_path = tmp_path / "state.db"
    captured: dict[str, object] = {}

    async def fake_test_feed(cfg: Config, db: Path, name: str, *, send: bool) -> None:
        captured["cfg"] = cfg
        captured["db"] = db
        captured["name"] = name
        captured["send"] = send

    monkeypatch.setattr(cli_module, "_test_feed_async", fake_test_feed)

    result = CliRunner().invoke(
        cli_module.app,
        ["test-feed", "ai", "--config", str(config_path), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert captured == {
        "cfg": captured["cfg"],
        "db": db_path,
        "name": "ai",
        "send": False,
    }
    assert isinstance(captured["cfg"], Config)


def test_test_feed_command_exits_for_unknown_feed(write_yaml, tmp_path: Path) -> None:
    config_path = write_yaml(_config_text())
    db_path = tmp_path / "state.db"

    result = CliRunner().invoke(
        cli_module.app,
        ["test-feed", "missing", "--config", str(config_path), "--db", str(db_path)],
    )

    assert result.exit_code == 1
    assert "no such feed: missing" in result.output


def test_send_now_command_forces_send(monkeypatch, write_yaml, tmp_path: Path) -> None:
    config_path = write_yaml(_config_text())
    db_path = tmp_path / "state.db"
    captured: dict[str, object] = {}

    async def fake_test_feed(cfg: Config, db: Path, name: str, *, send: bool) -> None:
        captured["cfg"] = cfg
        captured["db"] = db
        captured["name"] = name
        captured["send"] = send

    monkeypatch.setattr(cli_module, "_test_feed_async", fake_test_feed)

    result = CliRunner().invoke(
        cli_module.app,
        ["send-now", "ai", "--config", str(config_path), "--db", str(db_path)],
    )

    assert result.exit_code == 0
    assert captured["db"] == db_path
    assert captured["name"] == "ai"
    assert captured["send"] is True


def test_run_command_passes_health_port(monkeypatch, write_yaml, tmp_path: Path) -> None:
    config_path = write_yaml(_config_text())
    db_path = tmp_path / "state.db"
    captured: dict[str, object] = {}

    async def fake_run(cfg: Config, db: Path, health_port: int) -> None:
        captured["cfg"] = cfg
        captured["db"] = db
        captured["health_port"] = health_port

    monkeypatch.setattr(cli_module, "_run_async", fake_run)

    result = CliRunner().invoke(
        cli_module.app,
        [
            "run",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
            "--health-port",
            "9123",
        ],
    )

    assert result.exit_code == 0
    assert captured["db"] == db_path
    assert captured["health_port"] == 9123
    assert isinstance(captured["cfg"], Config)


def test_require_token_returns_env_value(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret")

    assert cli_module._require_token() == "secret"


def test_require_token_exits_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(typer.Exit) as exc:
        cli_module._require_token()

    assert exc.value.exit_code == 1


def test_optional_token_returns_env_value(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc")
    assert cli_module._optional_token() == "abc"


def test_optional_token_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert cli_module._optional_token() is None


def test_optional_token_returns_none_for_empty_value(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    assert cli_module._optional_token() is None


@pytest.mark.asyncio
async def test_test_feed_async_prints_messages_for_dry_run(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    cfg = _make_cfg("ai")
    observed: dict[str, object] = {}

    class FakeStore:
        def __init__(self, path: Path) -> None:
            observed["store_path"] = path
            observed["store"] = self
            self.closed = False

        async def open(self) -> None:
            observed["opened"] = True

        async def close(self) -> None:
            self.closed = True

    async def fake_run_feed_once(
        service_cfg: Config,
        store: FakeStore,
        name: str,
        *,
        dry_run: bool,
        telegram: object | None = None,
    ):  # type: ignore[no-untyped-def]
        observed["run_feed_once"] = (service_cfg, store, name, dry_run, telegram)
        return SimpleNamespace(
            feed=name,
            fetched=3,
            after_dedup=2,
            dropped=1,
            overflow=0,
            sent=0,
            duration_ms=12,
            skipped_reason=None,
            error=None,
            messages=["hello", "world"],
        )

    monkeypatch.setattr("glean.state.store.StateStore", FakeStore)
    monkeypatch.setattr("glean.api_service.run_feed_once", fake_run_feed_once)
    monkeypatch.setattr("glean.telegram.TelegramSender", object)

    await cli_module._test_feed_async(cfg, tmp_path / "state.db", "ai", send=False)

    output = capsys.readouterr().out
    assert "feed=ai fetched=3 after_dedup=2 dropped=1 overflow=0 sent=0 duration_ms=12" in output
    assert "---  WOULD SEND  ---" in output
    assert "[message 1]" in output
    service_cfg, service_store, service_name, dry_run, telegram = observed["run_feed_once"]
    assert service_cfg is cfg
    assert service_store is observed["store"]
    assert service_name == "ai"
    assert dry_run is True
    assert telegram is None
    assert observed["store"].closed is True


@pytest.mark.asyncio
async def test_test_feed_async_exits_when_feed_run_errors(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    cfg = _make_cfg("ai")
    observed: dict[str, object] = {}

    class FakeStore:
        def __init__(self, _path: Path) -> None:
            observed["store"] = self
            self.closed = False

        async def open(self) -> None:
            return None

        async def close(self) -> None:
            self.closed = True

    class FakeTelegramSender:
        def __init__(self, token: str) -> None:
            observed["token"] = token
            observed["telegram"] = self
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    async def fake_run_feed_once(
        service_cfg: Config,
        store: FakeStore,
        name: str,
        *,
        dry_run: bool,
        telegram: FakeTelegramSender | None = None,
    ):  # type: ignore[no-untyped-def]
        observed["run_feed_once"] = (service_cfg, store, name, dry_run, telegram)
        return SimpleNamespace(
            feed=name,
            fetched=1,
            after_dedup=1,
            dropped=0,
            overflow=0,
            sent=0,
            duration_ms=5,
            skipped_reason="bootstrap",
            error="boom",
            messages=[],
        )

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setattr("glean.state.store.StateStore", FakeStore)
    monkeypatch.setattr("glean.api_service.run_feed_once", fake_run_feed_once)
    monkeypatch.setattr("glean.telegram.TelegramSender", FakeTelegramSender)

    with pytest.raises(typer.Exit) as exc:
        await cli_module._test_feed_async(cfg, tmp_path / "state.db", "ai", send=True)

    output = capsys.readouterr().out
    assert exc.value.exit_code == 2
    assert "skipped: bootstrap" in output
    assert "error: boom" in output
    assert observed["token"] == "secret-token"
    service_cfg, service_store, service_name, dry_run, telegram = observed["run_feed_once"]
    assert service_cfg is cfg
    assert service_store is observed["store"]
    assert service_name == "ai"
    assert dry_run is False
    assert telegram is observed["telegram"]
    assert observed["telegram"].closed is True
    assert observed["store"].closed is True


@pytest.mark.asyncio
async def test_run_async_starts_scheduler_and_cleans_up(
    monkeypatch,
    tmp_path: Path,
) -> None:
    cfg = _make_cfg("ai")
    observed: dict[str, object] = {"logs": []}

    class FakeStore:
        def __init__(self, path: Path) -> None:
            observed["store_path"] = path
            observed["store"] = self
            self.closed = False

        async def open(self) -> None:
            observed["store_opened"] = True

        async def close(self) -> None:
            self.closed = True

    class FakeTelegramSender:
        def __init__(self, token: str) -> None:
            observed["token"] = token
            observed["telegram"] = self

    class FakeRunner:
        def __init__(
            self,
            _cfg: Config,
            store: FakeStore,
            telegram: FakeTelegramSender,
            *,
            event_bus: object | None = None,
        ) -> None:
            observed["runner"] = self
            observed["runner_store"] = store
            observed["runner_telegram"] = telegram
            observed["runner_event_bus"] = event_bus
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    event_bus = object()

    class FakeApiServer:
        def __init__(self) -> None:
            self.should_exit = False
            self.served = False
            self.config = SimpleNamespace(
                app=SimpleNamespace(state=SimpleNamespace(glean_event_bus=event_bus))
            )

        async def serve(self) -> None:
            self.served = True
            while not self.should_exit:
                await cli_module.asyncio.sleep(0)

    api_server = FakeApiServer()

    async def fake_run_api_server(store: FakeStore, db_path: Path, *, port: int) -> FakeApiServer:
        observed["api_store"] = store
        observed["api_db_path"] = db_path
        observed["api_port"] = port
        return api_server

    async def fake_schedule_feeds(scheduler: object, runner: FakeRunner) -> None:
        observed["schedule_args"] = (scheduler, runner)

    class FakeLoop:
        def __init__(self) -> None:
            self.handlers: list[object] = []

        def add_signal_handler(self, _sig: object, callback) -> None:  # type: ignore[no-untyped-def]
            self.handlers.append(callback)

    fake_loop = FakeLoop()

    class FakeAsyncScheduler:
        async def __aenter__(self) -> FakeAsyncScheduler:
            observed["scheduler"] = self
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def start_in_background(self) -> None:
            observed["scheduler_started"] = True
            for callback in list(fake_loop.handlers):
                callback()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "run-token")
    monkeypatch.setattr("glean.state.store.StateStore", FakeStore)
    monkeypatch.setattr("glean.telegram.TelegramSender", FakeTelegramSender)
    monkeypatch.setattr("glean.pipeline.engine.Runner", FakeRunner)
    monkeypatch.setattr("glean.api.app.run_api_server", fake_run_api_server)
    monkeypatch.setattr("glean.scheduler.schedule_feeds", fake_schedule_feeds)
    monkeypatch.setattr("apscheduler.AsyncScheduler", FakeAsyncScheduler)
    monkeypatch.setattr(cli_module.asyncio, "get_running_loop", lambda: fake_loop)
    monkeypatch.setattr(
        cli_module,
        "logger",
        SimpleNamespace(info=lambda event, **kwargs: observed["logs"].append((event, kwargs))),
    )

    await cli_module._run_async(cfg, tmp_path / "state.db", 9123)

    assert observed["token"] == "run-token"
    assert observed["api_db_path"] == tmp_path / "state.db"
    assert observed["api_port"] == 9123
    assert api_server.served is True
    assert api_server.should_exit is True
    assert observed["scheduler_started"] is True
    assert observed["runner_event_bus"] is event_bus
    assert observed["schedule_args"] == (observed["scheduler"], observed["runner"])
    assert observed["runner"].closed is True
    assert observed["store"].closed is True
    assert observed["logs"] == [
        ("daemon_started", {"feeds": 1}),
        ("shutdown_requested", {}),
    ]


def test_main_invokes_typer_app(monkeypatch) -> None:
    called: list[str] = []

    monkeypatch.setattr(cli_module, "app", lambda: called.append("called"))

    cli_module.main()

    assert called == ["called"]


def test_main_exits_with_130_on_keyboard_interrupt(monkeypatch) -> None:
    def raise_keyboard_interrupt() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_module, "app", raise_keyboard_interrupt)

    with pytest.raises(SystemExit, match="130"):
        cli_module.main()


def test_python_module_entrypoint_invokes_cli_app(monkeypatch) -> None:
    called: list[str] = []
    cli_app_module = importlib.import_module("glean.cli.app")

    monkeypatch.setattr(cli_app_module, "app", lambda: called.append("called"))

    runpy.run_module("glean.__main__", run_name="__main__")

    assert called == ["called"]
