"""Heartbeat sync: updates bot_status every N seconds with auto-reconnect."""

import logging
import threading

from .config import AgentConfig
from . import mt5_client
from .supabase_client import SupabaseAgentClient

logger = logging.getLogger(__name__)

MAX_FAILURES = 10


def run(stop_event: threading.Event, config: AgentConfig, sb: SupabaseAgentClient):
    consecutive_failures = 0

    while not stop_event.is_set():
        status_info = mt5_client.get_status_info(config)

        if status_info["status"] == "offline":
            logger.warning("MT5 disconnected — attempting reconnect...")
            if mt5_client.initialize(config):
                status_info["status"] = "online"
                consecutive_failures = 0
                logger.info("MT5 reconnected successfully")

        ok = sb.upsert_heartbeat(status_info)
        if ok:
            consecutive_failures = 0
            logger.debug("Heartbeat sent: %s", status_info["status"])
        else:
            consecutive_failures += 1
            logger.warning("Heartbeat failed (%d/%d)", consecutive_failures, MAX_FAILURES)
            if consecutive_failures >= MAX_FAILURES:
                logger.error("Too many consecutive heartbeat failures — stopping")
                break

        stop_event.wait(config.heartbeat_interval)
