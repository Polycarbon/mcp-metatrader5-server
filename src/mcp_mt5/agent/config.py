import os


class AgentConfig:
    def __init__(self):
        self.bot_id = os.getenv("BOT_ID", "peter-window-server")
        self.default_symbol = os.getenv("DEFAULT_SYMBOL", "BTCUSD")
        self.default_timeframe = os.getenv("DEFAULT_TIMEFRAME", "H1")
        self.default_mode = os.getenv("DEFAULT_MODE", "AI Autonomous")

        self.heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL", "5"))
        self.sync_interval = int(os.getenv("SYNC_INTERVAL", "10"))
        self.price_sync_interval = int(os.getenv("PRICE_SYNC_INTERVAL", "10"))
        self.command_poll_interval = int(os.getenv("COMMAND_POLL_INTERVAL", "2"))

        self.bulk_candle_count = int(os.getenv("BULK_CANDLE_COUNT", "500"))
        self.incremental_candle_count = int(os.getenv("INCREMENTAL_CANDLE_COUNT", "10"))
        self.price_batch_size = int(os.getenv("PRICE_BATCH_SIZE", "50"))

        symbols_str = os.getenv("PRICE_SYNC_SYMBOLS", "")
        self.price_sync_symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]

        self.mt5_login = int(os.getenv("MT5_LOGIN", "0"))
        self.mt5_password = os.getenv("MT5_PASSWORD", "")
        self.mt5_server = os.getenv("MT5_SERVER", "")
        self.mt5_path = os.getenv("MT5_PATH", "")
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
