"""Deals sync: fetches closed deal history from MT5 and upserts to Supabase."""

import logging
import threading
from datetime import datetime, timezone, timedelta

from . import mt5_client
from .supabase_client import SupabaseAgentClient
from .config import AgentConfig

logger = logging.getLogger(__name__)

MAX_FAILURES = 10
UPSERT_BATCH_SIZE = 500


def _deal_to_row(deal) -> dict:
    """Convert an MT5 deal object to a dict matching the Supabase deals table."""
    return {
        "ticket": deal.ticket,
        "order_ticket": deal.order,
        "position_id": deal.position_id,
        "symbol": deal.symbol,
        "deal_type": deal.type,
        "entry": deal.entry,
        "volume": deal.volume,
        "price": deal.price,
        "commission": deal.commission,
        "swap": deal.swap,
        "profit": deal.profit,
        "fee": deal.fee,
        "magic": deal.magic,
        "comment": deal.comment,
        "deal_time": datetime.fromtimestamp(deal.time, tz=timezone.utc).isoformat(),
        "deal_time_msc": deal.time_msc,
    }


def sync_once(sb: SupabaseAgentClient, lookback_seconds: int) -> bool:
    """Fetch recent deals and upsert them."""
    now = datetime.now(timezone.utc)
    from_dt = now - timedelta(seconds=lookback_seconds)

    deals = mt5_client.get_history_deals(from_dt, now)
    if deals is None:
        logger.warning("history_deals_get returned None")
        return True  # not a failure — just no data

    rows = [_deal_to_row(d) for d in deals]
    if not rows:
        logger.debug("No new deals in last %ds", lookback_seconds)
        return True

    ok = sb.upsert_deals(rows)
    if ok:
        logger.info("Synced %d deal(s)", len(rows))
    return ok


def backfill(sb: SupabaseAgentClient) -> bool:
    """One-time backfill of all available deal history."""
    logger.info("Starting deal history backfill...")
    from_dt = datetime(2000, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime.now(timezone.utc)

    deals = mt5_client.get_history_deals(from_dt, to_dt)
    if deals is None or len(deals) == 0:
        logger.info("No historical deals found")
        return True

    rows = [_deal_to_row(d) for d in deals]
    logger.info("Backfilling %d deal(s)...", len(rows))
    ok = sb.upsert_deals(rows)
    if ok:
        logger.info("Deal history backfill complete")
    return ok


def run(stop_event: threading.Event, config: AgentConfig, sb: SupabaseAgentClient):
    consecutive_failures = 0

    # Backfill on first run to catch anything missed while the daemon was down
    if not backfill(sb):
        logger.warning("Initial backfill failed — will retry via normal sync")

    while not stop_event.is_set():
        # Look back 2x the sync interval to avoid gaps
        lookback = config.deals_sync_interval * 2
        ok = sync_once(sb, lookback)
        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            logger.warning(
                "Deals sync failed (%d/%d)", consecutive_failures, MAX_FAILURES
            )
            if consecutive_failures >= MAX_FAILURES:
                logger.error("Too many deals sync failures — stopping")
                break

        stop_event.wait(config.deals_sync_interval)
