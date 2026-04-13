"""MT5 connection wrapper for the agent daemon."""

import logging

import MetaTrader5 as mt5

from .config import AgentConfig

logger = logging.getLogger(__name__)


def initialize(config: AgentConfig) -> bool:
    kwargs = {}
    if config.mt5_path:
        kwargs["path"] = config.mt5_path
    if config.mt5_login:
        kwargs["login"] = config.mt5_login
    if config.mt5_password:
        kwargs["password"] = config.mt5_password
    if config.mt5_server:
        kwargs["server"] = config.mt5_server

    if not mt5.initialize(**kwargs):
        error = mt5.last_error()
        logger.error("MT5 initialize failed: %s", error)
        return False

    account = mt5.account_info()
    if account is None:
        logger.error("Failed to get account info after init")
        mt5.shutdown()
        return False

    logger.info(
        "MT5 connected — account=%d server=%s balance=%.2f",
        account.login, account.server, account.balance,
    )
    return True


def is_connected() -> bool:
    info = mt5.terminal_info()
    if info is None:
        return False
    return info.connected


def get_status_info(config: AgentConfig) -> dict:
    connected = is_connected()
    return {
        "status": "online" if connected else "offline",
        "mode": config.default_mode,
        "symbol": config.default_symbol,
        "timeframe": config.default_timeframe,
    }


def get_account_info():
    return mt5.account_info()


def get_positions():
    return mt5.positions_get()


def close_all_positions() -> tuple[int, int]:
    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        logger.info("No open positions to close")
        return (0, 0)

    closed = 0
    failed = 0

    for pos in positions:
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": pos.ticket,
            "magic": 0,
            "comment": "emergency_stop",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is not None:
            request["price"] = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
            logger.info("Closed position #%d (%s %.2f lots)", pos.ticket, pos.symbol, pos.volume)
        else:
            error = result.comment if result else "order_send returned None"
            logger.error("Failed to close position #%d: %s", pos.ticket, error)
            failed += 1

    return (closed, failed)


def copy_rates_from_pos(symbol: str, timeframe: int, start_pos: int, count: int):
    return mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)


def shutdown():
    mt5.shutdown()
    logger.info("MT5 shutdown complete")
