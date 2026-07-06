"""news/sources/ — pluggable economic-calendar providers behind one CalendarSource interface.

ForexFactorySource (free faireconomy feed) is the only implementation today. A paid provider
(Trading Economics, …) would be a new file here implementing CalendarSource; the store and engine
are unaffected.
"""

from .base import CalendarSource, FetchResult
from .forex_factory import ForexFactorySource
from .forex_factory_history import ForexFactoryHistorySource

__all__ = ["CalendarSource", "FetchResult", "ForexFactorySource", "ForexFactoryHistorySource"]
