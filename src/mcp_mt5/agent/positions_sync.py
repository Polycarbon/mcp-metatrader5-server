"""Positions sync: upserts open positions, deletes closed ones."""

import logging
import threading
from datetime import datetime, timezone

from . import mt5_client
from .supabase_client import SupabaseAgentClient
from .config import AgentConfig

logger = logging.getLogger(__name__)

MAX_FAILURES = 10


def sync_once(sb: SupabaseAgentClient) -> bool:
    positions = mt5_client.get_positions()
    if positions is None:
        positions = ()

    now = datetime.now(timezone.utc).isoformat()
    open_tickets = []

    for pos in positions:
        open_tickets.append(pos.ticket)
        pos_type = "buy" if pos.type == 0 else "sell"

        position_data = {
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": pos_type,
            "volume": pos.volume,
            "open_price": pos.price_open,
            "current_price": pos.price_current,
            "profit": pos.profit,
            "open_time": datetime.fromtimestamp(pos.time, tz=timezone.utc).isoformat(),
            "updated_at": now,
        }

        if not sb.upsert_position(position_data):
            return False

    if not sb.delete_closed_positions(open_tickets):
        return False

    logger.debug("Positions synced — %d open", len(open_tickets))
    return True


def run(stop_event: threading.Event, config: AgentConfig, sb: SupabaseAgentClient):
    consecutive_failures = 0

    while not stop_event.is_set():
        ok = sync_once(sb)
        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            logger.warning("Positions sync failed (%d/%d)", consecutive_failures, MAX_FAILURES)
            if consecutive_failures >= MAX_FAILURES:
                logger.error("Too many positions sync failures — stopping")
                break

        stop_event.wait(config.sync_interval)
