import logging
from typing import Final

logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

class KalshiBot:
    """
    A minimal auto-trading bot that stores trading parameters and provides
    decision-making methods for entering and exiting trades.
    """
    def __init__(
        self,
        entry_price_low: float,
        entry_price_high: float,
        exit_price_profit: float,
        exit_price_loss: float,
        trade_size: int,
        profit_goal: float,
        max_drawdown: float
    ) -> None:
        self.entry_price_low: Final[float] = entry_price_low
        self.entry_price_high: Final[float] = entry_price_high
        self.exit_price_profit: Final[float] = exit_price_profit
        self.exit_price_loss: Final[float] = exit_price_loss
        self.trade_size: Final[int] = trade_size
        self.profit_goal: Final[float] = profit_goal
        self.max_drawdown: Final[float] = max_drawdown
        
        logging.warning(
            "KalshiBot init: entry_low=%.2f, entry_high=%.2f, exit_profit=%.2f, exit_loss=%.2f, trade_size=%d, profit_goal=%.2f, max_drawdown=%.2f",
            entry_price_low, entry_price_high, exit_price_profit,
            exit_price_loss, trade_size, profit_goal, max_drawdown
        )

    def should_enter_trade(self, current_price: float) -> bool:
        """
        Example logic: enter if current_price is between entry_price_low and entry_price_high.
        """
        return self.entry_price_low <= current_price <= self.entry_price_high

    def should_exit_trade(self, current_price: float, entry_price: float) -> str:
        """
        Returns "profit" if current_price >= exit_price_profit,
        "loss" if current_price <= exit_price_loss,
        or an empty string if neither condition is met.
        """
        if current_price >= self.exit_price_profit:
            return "profit"
        elif current_price <= self.exit_price_loss:
            return "loss"
        return ""
