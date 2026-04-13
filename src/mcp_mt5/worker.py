"""
Hourly worker: collects equity snapshots and deal history from MT5,
then upserts them into Supabase.

Run modes:
    python -m mcp_mt5.worker              # normal hourly loop
    python -m mcp_mt5.worker --init       # backfill all history then exit
    mt5worker                             # normal hourly loop (installed script)
    mt5worker --init                      # backfill all history then exit
"""

import logging
import os
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

INTERVAL_SECONDS = int(os.getenv("WORKER_INTERVAL_SECONDS", "3600"))

# Batch size for initial history backfill to avoid huge payloads
UPSERT_BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# MT5 helpers
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


def _collect_equity_snapshot() -> dict | None:
    info = mt5.account_info()
    if info is None:
        log.error("account_info() returned None: %s", mt5.last_error())
        return None

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "login": info.login,
        "currency": info.currency,
        "balance": info.balance,
        "equity": info.equity,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "profit": info.profit,
        "leverage": info.leverage,
    }


def _deal_to_row(d) -> dict:
    return {
        "ticket": d.ticket,
        "order_ticket": d.order,
        "position_id": d.position_id,
        "symbol": d.symbol,
        "deal_type": d.type,
        "entry": d.entry,
        "volume": d.volume,
        "price": d.price,
        "commission": d.commission,
        "swap": d.swap,
        "profit": d.profit,
        "fee": d.fee,
        "magic": d.magic,
        "comment": d.comment,
        "deal_time": datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
        "deal_time_msc": d.time_msc,
    }


def _collect_deals(from_dt: datetime, to_dt: datetime) -> list[dict]:
    deals = mt5.history_deals_get(from_dt, to_dt)
    if deals is None:
        log.warning("history_deals_get() returned None: %s", mt5.last_error())
        return []
    rows = [_deal_to_row(d) for d in deals]
    log.info("fetched %d deal(s) from %s to %s", len(rows), from_dt.isoformat(), to_dt.isoformat())
    return rows


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _supabase_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def _upsert_equity(client: Client, snapshot: dict) -> None:
    client.table("equity_snapshots").insert(snapshot).execute()
    log.info("equity snapshot written  equity=%.2f", snapshot["equity"])


def _upsert_deals(client: Client, deals: list[dict]) -> None:
    if not deals:
        log.info("no new deals in window")
        return
    # batch to avoid oversized payloads
    for i in range(0, len(deals), UPSERT_BATCH_SIZE):
        batch = deals[i : i + UPSERT_BATCH_SIZE]
        client.table("deals").upsert(batch, on_conflict="ticket").execute()
        log.info("upserted batch %d-%d (%d rows)", i + 1, i + len(batch), len(batch))


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

def run_once(client: Client) -> None:
    """Collect equity + last-hour deals and upsert."""
    now = datetime.now(timezone.utc)
    from_dt = datetime.fromtimestamp(now.timestamp() - INTERVAL_SECONDS, tz=timezone.utc)

    snapshot = _collect_equity_snapshot()
    if snapshot:
        _upsert_equity(client, snapshot)

    deals = _collect_deals(from_dt, now)
    _upsert_deals(client, deals)


def run_init_history(client: Client) -> None:
    """Backfill all available deal history from MT5 into Supabase."""
    log.info("Starting full history backfill …")

    # MT5 history starts from the account creation date; use epoch as safe lower bound
    from_dt = datetime(2000, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime.now(timezone.utc)

    deals = _collect_deals(from_dt, to_dt)
    if not deals:
        log.info("No historical deals found.")
        return

    log.info("Backfilling %d deal(s) total …", len(deals))
    _upsert_deals(client, deals)
    log.info("History backfill complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import warnings
    warnings.warn(
        "mt5worker is deprecated and will be removed in a future version. "
        "Use mt5agent instead, which includes all worker functionality.",
        DeprecationWarning,
        stacklevel=2,
    )
    print("\u26a0 DEPRECATED: mt5worker is deprecated. Use mt5agent instead.")

    init_mode = "--init" in sys.argv

    client = _supabase_client()

    if not _init_mt5():
        raise SystemExit("Could not connect to MT5")

    try:
        if init_mode:
            run_init_history(client)
        else:
            log.info("Worker starting  interval=%ds", INTERVAL_SECONDS)
            while True:
                try:
                    run_once(client)
                except Exception:
                    log.exception("run_once() failed — will retry next cycle")
                log.info("sleeping %ds …", INTERVAL_SECONDS)
                time.sleep(INTERVAL_SECONDS)
    finally:
        mt5.shutdown()
        log.info("MT5 connection closed")


if __name__ == "__main__":
    main()
