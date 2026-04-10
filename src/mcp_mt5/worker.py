"""
Hourly worker: collects equity snapshots and deal history from MT5,
then upserts them into Supabase.

Run directly:
    python -m mcp_mt5.worker

Or via the installed script:
    mt5worker
"""

import logging
import os
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

    log.info("MT5 connected (account %s)", mt5.account_info().login if mt5.account_info() else "unknown")
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
        "margin_free": info.free_margin,
        "profit": info.profit,
        "leverage": info.leverage,
    }


def _collect_deals(from_dt: datetime, to_dt: datetime) -> list[dict]:
    deals = mt5.history_deals_get(from_dt, to_dt)
    if deals is None:
        log.warning("history_deals_get() returned None: %s", mt5.last_error())
        return []

    rows = []
    for d in deals:
        rows.append({
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
        })
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
    # upsert on ticket so re-runs are idempotent
    client.table("deals").upsert(deals, on_conflict="ticket").execute()
    log.info("upserted %d deal(s)", len(deals))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_once(client: Client, window_seconds: int = INTERVAL_SECONDS) -> None:
    now = datetime.now(timezone.utc)
    from_dt = datetime.fromtimestamp(now.timestamp() - window_seconds, tz=timezone.utc)

    snapshot = _collect_equity_snapshot()
    if snapshot:
        _upsert_equity(client, snapshot)

    deals = _collect_deals(from_dt, now)
    _upsert_deals(client, deals)


def main() -> None:
    log.info("Worker starting  interval=%ds", INTERVAL_SECONDS)

    client = _supabase_client()

    if not _init_mt5():
        raise SystemExit("Could not connect to MT5")

    try:
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
