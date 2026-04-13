"""Command handler: polls Supabase commands table, executes start/stop/emergency."""

import logging
import threading

from . import mt5_client
from .supabase_client import SupabaseAgentClient
from .config import AgentConfig

logger = logging.getLogger(__name__)

MAX_FAILURES = 10


class CommandHandler:
    def __init__(self, config: AgentConfig, sb: SupabaseAgentClient):
        self.config = config
        self.sb = sb
        self._trading_active = threading.Event()
        self._trading_thread: threading.Thread | None = None
        self._trading_lock = threading.Lock()

    def _update_bot_status(self, status: str):
        try:
            info = mt5_client.get_status_info(self.config)
            info["status"] = status
            self.sb.upsert_heartbeat(info)
        except Exception:
            logger.exception("Failed to update bot status to %s", status)

    def _trading_loop(self, stop_event: threading.Event):
        logger.info("Trading loop started (symbol=%s, timeframe=%s)",
                     self.config.default_symbol, self.config.default_timeframe)
        while self._trading_active.is_set() and not stop_event.is_set():
            stop_event.wait(1)
        logger.info("Trading loop stopped")

    def _handle_start_bot(self, command: dict, stop_event: threading.Event):
        with self._trading_lock:
            if self._trading_active.is_set():
                logger.info("Trading already active — ignoring start_bot")
                self.sb.update_command_status(command["id"], "executed", error=None)
                return

            self._trading_active.set()
            self._trading_thread = threading.Thread(
                target=self._trading_loop, args=(stop_event,),
                name="trading-loop", daemon=True,
            )
            self._trading_thread.start()

        self._update_bot_status("online")
        self.sb.update_command_status(command["id"], "executed", error=None)
        logger.info("start_bot executed")

    def _handle_stop_bot(self, command: dict):
        with self._trading_lock:
            if not self._trading_active.is_set():
                logger.info("Trading not active — ignoring stop_bot")
                self.sb.update_command_status(command["id"], "executed", error=None)
                return

            self._trading_active.clear()
            if self._trading_thread is not None:
                self._trading_thread.join(timeout=5)
                self._trading_thread = None

        self._update_bot_status("offline")
        self.sb.update_command_status(command["id"], "executed", error=None)
        logger.info("stop_bot executed")

    def _handle_emergency_stop(self, command: dict):
        with self._trading_lock:
            self._trading_active.clear()
            if self._trading_thread is not None:
                self._trading_thread.join(timeout=5)
                self._trading_thread = None

        closed, failed = mt5_client.close_all_positions()
        if failed > 0:
            logger.error("Emergency stop: closed %d positions, %d failed", closed, failed)
            self.sb.update_command_status(
                command["id"], "failed",
                error=f"Closed {closed} positions but {failed} failed to close",
            )
        else:
            logger.info("Emergency stop: closed %d positions", closed)
            self.sb.update_command_status(command["id"], "executed", error=None)

        self._update_bot_status("offline")

    def process_command(self, command: dict, stop_event: threading.Event):
        cmd_type = command.get("command", "")
        cmd_id = command.get("id", "?")
        logger.info("Processing command: %s (id=%s)", cmd_type, cmd_id)

        handlers = {
            "start_bot": lambda cmd: self._handle_start_bot(cmd, stop_event),
            "stop_bot": lambda cmd: self._handle_stop_bot(cmd),
            "emergency_stop": lambda cmd: self._handle_emergency_stop(cmd),
        }

        handler = handlers.get(cmd_type)
        if handler is None:
            logger.warning("Unknown command type: %s", cmd_type)
            self.sb.update_command_status(cmd_id, "failed", error=f"Unknown command: {cmd_type}")
            return

        try:
            handler(command)
        except Exception as exc:
            logger.exception("Command %s failed", cmd_type)
            self.sb.update_command_status(cmd_id, "failed", error=str(exc))

    def shutdown(self):
        with self._trading_lock:
            self._trading_active.clear()


def run(stop_event: threading.Event, config: AgentConfig, sb: SupabaseAgentClient):
    handler = CommandHandler(config, sb)

    while not stop_event.is_set():
        commands = sb.get_pending_commands()
        for cmd in commands:
            if stop_event.is_set():
                break
            handler.process_command(cmd, stop_event)

        stop_event.wait(config.command_poll_interval)

    handler.shutdown()
    logger.info("Command handler stopped")
