import pytest


@pytest.mark.unit
class TestAgentConfig:
    def test_defaults(self, monkeypatch):
        for key in [
            "BOT_ID", "DEFAULT_SYMBOL", "DEFAULT_TIMEFRAME", "DEFAULT_MODE",
            "SYNC_INTERVAL", "PRICE_SYNC_INTERVAL", "PRICE_SYNC_SYMBOLS",
            "BULK_CANDLE_COUNT", "INCREMENTAL_CANDLE_COUNT", "PRICE_BATCH_SIZE",
            "COMMAND_POLL_INTERVAL", "HEARTBEAT_INTERVAL",
        ]:
            monkeypatch.delenv(key, raising=False)

        from mcp_mt5.agent.config import AgentConfig
        cfg = AgentConfig()

        assert cfg.bot_id == "peter-window-server"
        assert cfg.default_symbol == "BTCUSD"
        assert cfg.default_timeframe == "H1"
        assert cfg.default_mode == "AI Autonomous"
        assert cfg.sync_interval == 10
        assert cfg.price_sync_interval == 10
        assert cfg.heartbeat_interval == 5
        assert cfg.bulk_candle_count == 500
        assert cfg.incremental_candle_count == 10
        assert cfg.price_batch_size == 50
        assert cfg.command_poll_interval == 2
        assert cfg.price_sync_symbols == []

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("BOT_ID", "test-bot")
        monkeypatch.setenv("DEFAULT_SYMBOL", "EURUSD")
        monkeypatch.setenv("SYNC_INTERVAL", "30")
        monkeypatch.setenv("PRICE_SYNC_SYMBOLS", "BTCUSD,EURUSD,XAUUSD")

        from mcp_mt5.agent.config import AgentConfig
        cfg = AgentConfig()

        assert cfg.bot_id == "test-bot"
        assert cfg.default_symbol == "EURUSD"
        assert cfg.sync_interval == 30
        assert cfg.price_sync_symbols == ["BTCUSD", "EURUSD", "XAUUSD"]

    def test_empty_symbols_string(self, monkeypatch):
        monkeypatch.setenv("PRICE_SYNC_SYMBOLS", "")

        from mcp_mt5.agent.config import AgentConfig
        cfg = AgentConfig()

        assert cfg.price_sync_symbols == []
