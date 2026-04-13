import pytest
import threading
from unittest.mock import MagicMock, patch


@pytest.mark.unit
class TestRunner:
    @patch("mcp_mt5.agent.runner.mt5_client")
    @patch("mcp_mt5.agent.runner.SupabaseAgentClient")
    def test_build_threads_returns_five(self, mock_sb_cls, mock_mt5):
        from mcp_mt5.agent.runner import build_threads
        from mcp_mt5.agent.config import AgentConfig

        config = AgentConfig()
        sb = MagicMock()
        stop_event = threading.Event()

        threads = build_threads(stop_event, config, sb)

        assert len(threads) == 5
        names = {t.name for t in threads}
        assert names == {"heartbeat", "account-sync", "positions-sync", "price-sync", "command-handler"}
        for t in threads:
            assert t.daemon is True

    @patch("mcp_mt5.agent.runner.mt5_client")
    @patch("mcp_mt5.agent.runner.SupabaseAgentClient")
    @patch("mcp_mt5.agent.heartbeat.mt5_client")
    @patch("mcp_mt5.agent.heartbeat.SupabaseAgentClient", new=MagicMock)
    @patch("mcp_mt5.agent.account_sync.mt5_client")
    @patch("mcp_mt5.agent.positions_sync.mt5_client")
    @patch("mcp_mt5.agent.price_sync.mt5_client")
    @patch("mcp_mt5.agent.command_handler.mt5_client")
    def test_threads_start_and_stop(
        self, mock_cmd_mt5, mock_price_mt5, mock_pos_mt5,
        mock_acct_mt5, mock_hb_mt5, mock_sb_cls, mock_mt5,
    ):
        from mcp_mt5.agent.runner import build_threads
        from mcp_mt5.agent.config import AgentConfig

        config = AgentConfig()
        sb = MagicMock()
        stop_event = threading.Event()

        # Configure mocks so loops don't crash
        for m in (mock_mt5, mock_hb_mt5, mock_acct_mt5, mock_pos_mt5, mock_price_mt5, mock_cmd_mt5):
            m.get_status_info.return_value = {"status": "online", "mode": "test", "symbol": "BTCUSD", "timeframe": "H1"}
            m.initialize.return_value = True
            m.get_account_info.return_value = MagicMock(
                login=123, currency="USD", balance=1000.0, equity=1000.0,
                margin=0.0, margin_free=1000.0, profit=0.0, leverage=100,
            )
            m.get_positions.return_value = ()
            m.copy_rates_from_pos.return_value = []
            m.close_all_positions.return_value = (0, 0)

        # Supabase mock returns
        sb.upsert_heartbeat.return_value = True
        sb.insert_account_snapshot.return_value = True
        sb.upsert_position.return_value = True
        sb.delete_closed_positions.return_value = True
        sb.upsert_price_data.return_value = True
        sb.get_pending_commands.return_value = []
        sb.get_bot_status_config.return_value = {"symbol": "BTCUSD"}

        threads = build_threads(stop_event, config, sb)

        for t in threads:
            t.start()

        for t in threads:
            assert t.is_alive()

        stop_event.set()
        for t in threads:
            t.join(timeout=5)

        for t in threads:
            assert not t.is_alive()
