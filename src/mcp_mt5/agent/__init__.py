"""PeterQuant Agent — real-time MT5-to-Supabase sync daemon."""

import logging
import signal
import sys
import threading

from dotenv import load_dotenv


def main():
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("agent")

    from .config import AgentConfig
    from . import mt5_client
    from .supabase_client import SupabaseAgentClient
    from .runner import build_threads

    config = AgentConfig()
    stop_event = threading.Event()

    def handle_signal(signum, frame):
        logger.info("Received signal %d — shutting down...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("Starting PeterQuant Agent...")

    if not mt5_client.initialize(config):
        logger.error("Failed to connect to MT5 — exiting")
        sys.exit(1)

    sb = SupabaseAgentClient(config)
    threads = build_threads(stop_event, config, sb)

    logger.info(
        "Starting heartbeat (every %ds), sync loops (every %ds), "
        "price sync (every %ds), command handler (every %ds)...",
        config.heartbeat_interval, config.sync_interval,
        config.price_sync_interval, config.command_poll_interval,
    )

    for t in threads:
        t.start()

    try:
        while not stop_event.is_set():
            stop_event.wait(1)
    finally:
        stop_event.set()
        for t in threads:
            t.join(timeout=5)
        mt5_client.shutdown()
        logger.info("Agent stopped.")
