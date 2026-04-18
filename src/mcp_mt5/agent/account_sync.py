"""Account sync: snapshots account balance/equity to Supabase."""

import logging
import threading
from datetime import datetime, timezone

from . import mt5_client
from .supabase_client import SupabaseAgentClient
from .config import AgentConfig

logger = logging.getLogger(__name__)

MAX_FAILURES = 10


def sync_once(sb: SupabaseAgentClient) -> bool:
    account = mt5_client.get_account_info()
    if account is None:
        logger.error("Failed to get account info")
        return False

    snapshot = {
        "id": 1,
        "balance": account.balance,
        "equity": account.equity,
        "margin": account.margin,
        "free_margin": account.margin_free,
        "unrealized_pl": account.profit,
        "daily_pl": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    ok = sb.upsert_account_snapshot(snapshot)
    if ok:
        logger.debug(
            "Account snapshot — balance=%.2f equity=%.2f unrealized_pl=%.2f",
            account.balance, account.equity, account.profit,
        )
    return ok


def run(stop_event: threading.Event, config: AgentConfig, sb: SupabaseAgentClient):
    consecutive_failures = 0

    while not stop_event.is_set():
        ok = sync_once(sb)
        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            logger.warning("Account sync failed (%d/%d)", consecutive_failures, MAX_FAILURES)
            if consecutive_failures >= MAX_FAILURES:
                logger.error("Too many account sync failures — stopping")
                break

        stop_event.wait(config.sync_interval)
