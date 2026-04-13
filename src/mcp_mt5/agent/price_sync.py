"""Price sync: OHLCV candle data with bulk/incremental strategy and retention."""

import logging
import threading
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5

from . import mt5_client
from .supabase_client import SupabaseAgentClient
from .config import AgentConfig

logger = logging.getLogger(__name__)

MAX_FAILURES = 10

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

RETENTION_DAYS = {
    "M1": 30,
    "M5": 60,
    "M15": 90,
    "H1": 365,
    "H4": 730,
    "D1": None,
}


class PriceSyncer:
    def __init__(self, config: AgentConfig, sb: SupabaseAgentClient):
        self.config = config
        self.sb = sb
        self._bulk_loaded: set[tuple[str, str]] = set()

    def _get_symbols(self) -> list[str]:
        if self.config.price_sync_symbols:
            return self.config.price_sync_symbols
        row = self.sb.get_bot_status_config()
        if row:
            symbol = (row.get("symbol") or "").strip()
            if symbol:
                return [symbol]
        if self.config.default_symbol:
            return [self.config.default_symbol]
        return []

    def _sync_symbol_timeframe(self, symbol: str, timeframe: str) -> bool:
        key = (symbol, timeframe)
        need_bulk = key not in self._bulk_loaded
        count = self.config.bulk_candle_count if need_bulk else self.config.incremental_candle_count

        mt5_tf = TIMEFRAME_MAP[timeframe]
        rates = mt5_client.copy_rates_from_pos(symbol, mt5_tf, 0, count)
        if rates is None:
            logger.error("copy_rates_from_pos failed for %s %s", symbol, timeframe)
            return False

        if len(rates) == 0:
            logger.debug("No candle data for %s %s", symbol, timeframe)
            return True

        rows = []
        for r in rates:
            rows.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "time": datetime.fromtimestamp(int(r["time"]), tz=timezone.utc).isoformat(),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["tick_volume"]),
            })

        for i in range(0, len(rows), self.config.price_batch_size):
            batch = rows[i : i + self.config.price_batch_size]
            if not self.sb.upsert_price_data(batch):
                return False

        if need_bulk:
            self._bulk_loaded.add(key)
            logger.info("Bulk loaded %d candles for %s %s", len(rates), symbol, timeframe)
            self._cleanup_old_data(symbol, timeframe)
        else:
            logger.debug("Incremental sync: %d candles for %s %s", len(rates), symbol, timeframe)

        return True

    def _cleanup_old_data(self, symbol: str, timeframe: str) -> None:
        retention = RETENTION_DAYS.get(timeframe)
        if retention is None:
            return
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention)).isoformat()
        self.sb.delete_old_price_data(symbol, timeframe, cutoff)

    def sync_once(self) -> bool:
        symbols = self._get_symbols()
        if not symbols:
            logger.debug("No symbols configured — skipping price sync")
            return True

        all_ok = True
        for symbol in symbols:
            for timeframe in TIMEFRAME_MAP:
                if not self._sync_symbol_timeframe(symbol, timeframe):
                    all_ok = False
        return all_ok


def run(stop_event: threading.Event, config: AgentConfig, sb: SupabaseAgentClient):
    syncer = PriceSyncer(config, sb)
    consecutive_failures = 0

    while not stop_event.is_set():
        ok = syncer.sync_once()
        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            logger.warning("Price sync failed (%d/%d)", consecutive_failures, MAX_FAILURES)
            if consecutive_failures >= MAX_FAILURES:
                logger.error("Too many price sync failures — stopping")
                break

        stop_event.wait(config.price_sync_interval)
