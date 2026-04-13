import pytest
from unittest.mock import MagicMock


@pytest.mark.unit
class TestSupabaseClient:
    def _make_client(self):
        from mcp_mt5.agent.supabase_client import SupabaseAgentClient
        client = SupabaseAgentClient.__new__(SupabaseAgentClient)
        client._client = MagicMock()
        client._bot_status_id = None
        return client

    def test_insert_account_snapshot(self):
        client = self._make_client()
        snapshot = {"balance": 1000.0, "equity": 1050.0}
        result = client.insert_account_snapshot(snapshot)
        assert result is True
        client._client.table.assert_called_with("equity_snapshots")

    def test_upsert_position(self):
        client = self._make_client()
        position = {"ticket": 123, "symbol": "BTCUSD", "type": "buy"}
        result = client.upsert_position(position)
        assert result is True

    def test_upsert_price_data(self):
        client = self._make_client()
        rows = [{"symbol": "BTCUSD", "timeframe": "H1", "time": "2026-04-13T00:00:00"}]
        result = client.upsert_price_data(rows)
        assert result is True

    def test_delete_closed_positions_with_open_tickets(self):
        client = self._make_client()
        result = client.delete_closed_positions([100, 200])
        assert result is True

    def test_delete_closed_positions_none_open(self):
        client = self._make_client()
        result = client.delete_closed_positions([])
        assert result is True

    def test_insert_snapshot_exception_returns_false(self):
        client = self._make_client()
        client._client.table.side_effect = Exception("connection error")
        result = client.insert_account_snapshot({"balance": 0})
        assert result is False

    def test_get_pending_commands(self):
        client = self._make_client()
        mock_result = MagicMock()
        mock_result.data = [{"id": "1", "command": "start_bot", "status": "pending"}]
        client._client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result
        result = client.get_pending_commands()
        assert result == [{"id": "1", "command": "start_bot", "status": "pending"}]
