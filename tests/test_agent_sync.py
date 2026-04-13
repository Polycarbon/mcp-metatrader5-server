"""Unit tests for agent sync modules."""

import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


@pytest.fixture
def mock_sb():
    return MagicMock()


@pytest.fixture
def agent_config():
    from mcp_mt5.agent.config import AgentConfig
    return AgentConfig()


@pytest.mark.unit
class TestAccountSync:
    @pytest.fixture(autouse=True)
    def _patch_mt5(self):
        with patch("mcp_mt5.agent.account_sync.mt5_client") as self.mock_mt5:
            yield

    def test_sync_once_success(self, mock_sb):
        from mcp_mt5.agent.account_sync import sync_once

        self.mock_mt5.get_account_info.return_value = SimpleNamespace(
            login=12345, currency="USD", balance=10000.0, equity=10500.0,
            margin=100.0, margin_free=10400.0, profit=500.0, leverage=100,
        )
        mock_sb.insert_account_snapshot.return_value = True

        result = sync_once(mock_sb)

        assert result is True
        mock_sb.insert_account_snapshot.assert_called_once()
        snapshot = mock_sb.insert_account_snapshot.call_args[0][0]
        assert snapshot["login"] == 12345
        assert snapshot["balance"] == 10000.0
        assert snapshot["equity"] == 10500.0

    def test_sync_once_mt5_returns_none(self, mock_sb):
        from mcp_mt5.agent.account_sync import sync_once

        self.mock_mt5.get_account_info.return_value = None

        result = sync_once(mock_sb)

        assert result is False
        mock_sb.insert_account_snapshot.assert_not_called()


@pytest.mark.unit
class TestPositionsSync:
    @pytest.fixture(autouse=True)
    def _patch_mt5(self):
        with patch("mcp_mt5.agent.positions_sync.mt5_client") as self.mock_mt5:
            yield

    def test_sync_once_with_positions(self, mock_sb):
        from mcp_mt5.agent.positions_sync import sync_once

        pos = SimpleNamespace(
            ticket=100, symbol="BTCUSD", type=0,
            volume=0.1, price_open=50000.0, price_current=51000.0,
            profit=100.0, time=1712966400,
        )
        self.mock_mt5.get_positions.return_value = [pos]
        mock_sb.upsert_position.return_value = True
        mock_sb.delete_closed_positions.return_value = True

        result = sync_once(mock_sb)

        assert result is True
        mock_sb.upsert_position.assert_called_once()
        position_data = mock_sb.upsert_position.call_args[0][0]
        assert position_data["ticket"] == 100
        assert position_data["type"] == "buy"
        mock_sb.delete_closed_positions.assert_called_once_with([100])

    def test_sync_once_no_positions(self, mock_sb):
        from mcp_mt5.agent.positions_sync import sync_once

        self.mock_mt5.get_positions.return_value = ()
        mock_sb.delete_closed_positions.return_value = True

        result = sync_once(mock_sb)

        assert result is True
        mock_sb.upsert_position.assert_not_called()
        mock_sb.delete_closed_positions.assert_called_once_with([])


@pytest.mark.unit
class TestPriceSync:
    @pytest.fixture(autouse=True)
    def _patch(self):
        with patch("mcp_mt5.agent.price_sync.mt5_client") as self.mock_mt5:
            yield

    def test_sync_symbol_timeframe_bulk(self, mock_sb, agent_config):
        from mcp_mt5.agent.price_sync import PriceSyncer

        syncer = PriceSyncer(agent_config, mock_sb)

        import numpy as np
        rates = np.array(
            [(1712966400, 50000.0, 51000.0, 49000.0, 50500.0, 100, 0, 0)],
            dtype=[
                ("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
                ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8"),
            ],
        )
        self.mock_mt5.copy_rates_from_pos.return_value = rates
        mock_sb.upsert_price_data.return_value = True

        result = syncer._sync_symbol_timeframe("BTCUSD", "H1")

        assert result is True
        mock_sb.upsert_price_data.assert_called_once()
        rows = mock_sb.upsert_price_data.call_args[0][0]
        assert rows[0]["symbol"] == "BTCUSD"
        assert rows[0]["timeframe"] == "H1"
        assert rows[0]["open"] == 50000.0
