import pytest
import threading
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_sb():
    return MagicMock()


@pytest.fixture
def mock_cmd_mt5():
    with patch("mcp_mt5.agent.command_handler.mt5_client") as mock:
        yield mock


@pytest.fixture
def agent_config():
    from mcp_mt5.agent.config import AgentConfig
    return AgentConfig()


@pytest.mark.unit
class TestCommandHandler:
    def test_handle_start_bot(self, mock_sb, mock_cmd_mt5, agent_config):
        from mcp_mt5.agent.command_handler import CommandHandler

        handler = CommandHandler(agent_config, mock_sb)
        stop_event = threading.Event()
        cmd = {"id": "cmd-1", "command": "start_bot"}

        handler.process_command(cmd, stop_event)

        mock_sb.update_command_status.assert_called_with("cmd-1", "executed", error=None)

    def test_handle_stop_bot(self, mock_sb, mock_cmd_mt5, agent_config):
        from mcp_mt5.agent.command_handler import CommandHandler

        handler = CommandHandler(agent_config, mock_sb)
        stop_event = threading.Event()

        handler.process_command({"id": "cmd-1", "command": "start_bot"}, stop_event)
        handler.process_command({"id": "cmd-2", "command": "stop_bot"}, stop_event)

        mock_sb.update_command_status.assert_any_call("cmd-2", "executed", error=None)

    def test_handle_emergency_stop(self, mock_sb, mock_cmd_mt5, agent_config):
        from mcp_mt5.agent.command_handler import CommandHandler

        handler = CommandHandler(agent_config, mock_sb)
        stop_event = threading.Event()
        mock_cmd_mt5.close_all_positions.return_value = (3, 0)

        handler.process_command({"id": "cmd-1", "command": "emergency_stop"}, stop_event)

        mock_cmd_mt5.close_all_positions.assert_called_once()
        mock_sb.update_command_status.assert_called_with("cmd-1", "executed", error=None)

    def test_handle_emergency_stop_with_failures(self, mock_sb, mock_cmd_mt5, agent_config):
        from mcp_mt5.agent.command_handler import CommandHandler

        handler = CommandHandler(agent_config, mock_sb)
        stop_event = threading.Event()
        mock_cmd_mt5.close_all_positions.return_value = (2, 1)

        handler.process_command({"id": "cmd-1", "command": "emergency_stop"}, stop_event)

        mock_sb.update_command_status.assert_called_with(
            "cmd-1", "failed", error="Closed 2 positions but 1 failed to close"
        )

    def test_unknown_command(self, mock_sb, mock_cmd_mt5, agent_config):
        from mcp_mt5.agent.command_handler import CommandHandler

        handler = CommandHandler(agent_config, mock_sb)
        stop_event = threading.Event()

        handler.process_command({"id": "cmd-1", "command": "unknown_cmd"}, stop_event)

        mock_sb.update_command_status.assert_called_with(
            "cmd-1", "failed", error="Unknown command: unknown_cmd"
        )
