"""Thread orchestrator: spawns and manages 5 daemon sync threads."""

import logging
import threading

from . import mt5_client
from .config import AgentConfig
from .supabase_client import SupabaseAgentClient
from . import heartbeat
from . import account_sync
from . import deals_sync
from . import positions_sync
from . import command_handler

logger = logging.getLogger(__name__)


def build_threads(
    stop_event: threading.Event,
    config: AgentConfig,
    sb: SupabaseAgentClient,
) -> list[threading.Thread]:
    """Create daemon threads. Does not start them."""
    return [
        threading.Thread(
            target=heartbeat.run, args=(stop_event, config, sb),
            name="heartbeat", daemon=True,
        ),
        threading.Thread(
            target=account_sync.run, args=(stop_event, config, sb),
            name="account-sync", daemon=True,
        ),
        threading.Thread(
            target=positions_sync.run, args=(stop_event, config, sb),
            name="positions-sync", daemon=True,
        ),
        threading.Thread(
            target=deals_sync.run, args=(stop_event, config, sb),
            name="deals-sync", daemon=True,
        ),
        # TODO: re-enable when ready
        # threading.Thread(
        #     target=price_sync.run, args=(stop_event, config, sb),
        #     name="price-sync", daemon=True,
        # ),
        threading.Thread(
            target=command_handler.run, args=(stop_event, config, sb),
            name="command-handler", daemon=True,
        ),
    ]
