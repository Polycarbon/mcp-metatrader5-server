"""Supabase operations for the agent daemon."""

import logging
from datetime import datetime, timezone

from supabase import create_client, Client

from .config import AgentConfig

logger = logging.getLogger(__name__)


class SupabaseAgentClient:
    def __init__(self, config: AgentConfig):
        self._client: Client = create_client(config.supabase_url, config.supabase_service_key)
        self._bot_status_id: int | None = None

    def upsert_heartbeat(self, status_info: dict) -> bool:
        try:
            now = datetime.now(timezone.utc).isoformat()
            if self._bot_status_id is not None:
                data = {**status_info, "last_heartbeat": now, "updated_at": now}
                self._client.table("bot_status").update(data).eq("id", self._bot_status_id).execute()
            else:
                result = self._client.table("bot_status").select("id").limit(1).execute()
                if result.data:
                    self._bot_status_id = result.data[0]["id"]
                    data = {**status_info, "last_heartbeat": now, "updated_at": now}
                    self._client.table("bot_status").update(data).eq("id", self._bot_status_id).execute()
                else:
                    data = {**status_info, "last_heartbeat": now}
                    result = self._client.table("bot_status").insert(data).execute()
                    if result.data:
                        self._bot_status_id = result.data[0]["id"]
            return True
        except Exception:
            logger.exception("Failed to upsert heartbeat")
            return False

    def upsert_account_snapshot(self, snapshot: dict) -> bool:
        try:
            self._client.table("account_snapshot").upsert(snapshot, on_conflict="id").execute()
            return True
        except Exception:
            logger.exception("Failed to upsert account snapshot")
            return False

    def upsert_deals(self, deals: list[dict], batch_size: int = 500) -> bool:
        """Upsert deal rows in batches to avoid oversized payloads."""
        try:
            for i in range(0, len(deals), batch_size):
                batch = deals[i : i + batch_size]
                self._client.table("deals").upsert(batch, on_conflict="ticket").execute()
                logger.info("Upserted deals batch %d-%d (%d rows)", i + 1, i + len(batch), len(batch))
            return True
        except Exception:
            logger.exception("Failed to upsert deals")
            return False

    def upsert_position(self, position: dict) -> bool:
        try:
            self._client.table("positions").upsert(position, on_conflict="ticket").execute()
            return True
        except Exception:
            logger.exception("Failed to upsert position")
            return False

    def upsert_price_data(self, rows: list[dict]) -> bool:
        try:
            self._client.table("price_data").upsert(rows, on_conflict="symbol,timeframe,time").execute()
            return True
        except Exception:
            logger.exception("Failed to upsert price data")
            return False

    def get_bot_status_config(self) -> dict | None:
        try:
            result = self._client.table("bot_status").select("symbol, timeframe").limit(1).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception:
            logger.exception("Failed to read bot_status config")
            return None

    def delete_old_price_data(self, symbol: str, timeframe: str, cutoff_iso: str) -> bool:
        try:
            self._client.table("price_data").delete().eq(
                "symbol", symbol
            ).eq("timeframe", timeframe).lt("time", cutoff_iso).execute()
            logger.info("Cleaned up old %s %s candles before %s", symbol, timeframe, cutoff_iso[:10])
            return True
        except Exception:
            logger.exception("Failed to delete old price data")
            return False

    def delete_closed_positions(self, open_tickets: list[int]) -> bool:
        try:
            if open_tickets:
                self._client.table("positions").delete().not_.in_("ticket", open_tickets).execute()
            else:
                self._client.table("positions").delete().neq("ticket", 0).execute()
            return True
        except Exception:
            logger.exception("Failed to delete closed positions")
            return False

    def get_pending_commands(self) -> list[dict]:
        try:
            result = (
                self._client.table("commands")
                .select("*")
                .eq("status", "pending")
                .order("created_at", desc=False)
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception("Failed to fetch pending commands")
            return []

    def update_command_status(self, command_id: str, status: str, error: str | None = None) -> None:
        data = {
            "status": status,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            data["payload"] = {"error": error}
        try:
            self._client.table("commands").update(data).eq("id", command_id).execute()
        except Exception:
            logger.exception("Failed to update command %s status to %s", command_id, status)
