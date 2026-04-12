"""
Heartbeat agent: sends bot status to Supabase every N seconds.

Run modes:
    python -m mcp_mt5.heartbeat          # default 5-second heartbeat
    mt5heartbeat                         # installed script
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "5"))
DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTCUSD")
DEFAULT_TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME", "H1")
DEFAULT_MODE = os.getenv("DEFAULT_MODE", "running")

_stop = False
_status_row_id: int | None = None


# ---------------------------------------------------------------------------
# MT5
# ---------------------------------------------------------------------------

def _init_mt5() -> bool:
    path = os.getenv("MT5_PATH")
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")

    kwargs: dict = {}
    if path:
        kwargs["path"] = path

    if not mt5.initialize(**kwargs):
        log.error("mt5.initialize() failed: %s", mt5.last_error())
        return False

    if login and password and server:
        if not mt5.login(int(login), password=password, server=server):
            log.error("mt5.login() failed: %s", mt5.last_error())
            mt5.shutdown()
            return False

    info = mt5.account_info()
    log.info("MT5 connected (account %s)", info.login if info else "unknown")
    return True


def _is_connected() -> bool:
    info = mt5.terminal_info()
    return info is not None and info.connected


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

def _supabase_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def _send_heartbeat(client: Client, status_info: dict) -> bool:
    """Insert or update a single bot_status row."""
    global _status_row_id
    now = datetime.now(timezone.utc).isoformat()

    try:
        if _status_row_id is not None:
            client.table("bot_status").update({
                **status_info,
                "last_heartbeat": now,
                "updated_at": now,
            }).eq("id", _status_row_id).execute()
        else:
            # First run: check if a row already exists
            resp = client.table("bot_status").select("id").limit(1).execute()
            if resp.data:
                _status_row_id = resp.data[0]["id"]
                client.table("bot_status").update({
                    **status_info,
                    "last_heartbeat": now,
                    "updated_at": now,
                }).eq("id", _status_row_id).execute()
            else:
                resp = client.table("bot_status").insert({
                    **status_info,
                    "last_heartbeat": now,
                }).execute()
                _status_row_id = resp.data[0]["id"]
        return True
    except Exception:
        log.exception("Failed to send heartbeat")
        return False


# ---------------------------------------------------------------------------
# Heartbeat loop
# ---------------------------------------------------------------------------

def _build_status() -> dict:
    connected = _is_connected()
    return {
        "status": "online" if connected else "offline",
        "mode": DEFAULT_MODE,
        "symbol": DEFAULT_SYMBOL,
        "timeframe": DEFAULT_TIMEFRAME,
    }


def _run_loop(client: Client) -> None:
    consecutive_failures = 0
    max_failures = 10

    while not _stop:
        status = _build_status()

        if status["status"] == "offline":
            log.warning("MT5 disconnected — attempting reconnect …")
            if _init_mt5():
                status["status"] = "online"
                consecutive_failures = 0
                log.info("MT5 reconnected")

        ok = _send_heartbeat(client, status)
        if ok:
            consecutive_failures = 0
            log.debug("heartbeat sent: %s", status["status"])
        else:
            consecutive_failures += 1
            log.warning("heartbeat failed (%d/%d)", consecutive_failures, max_failures)
            if consecutive_failures >= max_failures:
                log.error("Too many consecutive failures — stopping")
                break

        time.sleep(HEARTBEAT_INTERVAL)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _handle_signal(signum, _frame):
    global _stop
    log.info("Received signal %d — shutting down …", signum)
    _stop = True


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log.info("Starting heartbeat agent (every %ds) …", HEARTBEAT_INTERVAL)

    if not _init_mt5():
        log.error("Cannot connect to MT5 — exiting")
        sys.exit(1)

    client = _supabase_client()

    try:
        _run_loop(client)
    finally:
        # Send final offline status before exiting
        try:
            _send_heartbeat(client, {
                "status": "offline",
                "mode": "stopped",
                "symbol": DEFAULT_SYMBOL,
                "timeframe": DEFAULT_TIMEFRAME,
            })
        except Exception:
            pass
        mt5.shutdown()
        log.info("MT5 connection closed")


if __name__ == "__main__":
    main()
