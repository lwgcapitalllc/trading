"""news/sources/ — pluggable economic-calendar providers behind one CalendarSource interface.

Two free providers today: ForexFactorySource (faireconomy weekly feed, carries bank holidays) and
TradingViewSource (arbitrary date window + `actual` results, used by the live calendar tab). A paid
provider (Trading Economics, …) would be a new file here implementing CalendarSource; the store and
engine are unaffected.
"""

from .base import CalendarSource, FetchResult
from .forex_factory import ForexFactorySource
from .forex_factory_history import ForexFactoryHistorySource
from .tradingview import TradingViewSource

__all__ = [
    "CalendarSource",
    "FetchResult",
    "ForexFactorySource",
    "ForexFactoryHistorySource",
    "TradingViewSource",
]
