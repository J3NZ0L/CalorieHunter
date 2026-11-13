from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def today(self) -> date: ...
    def now(self) -> datetime: ...


class SystemClock:
    def today(self) -> date:
        return datetime.now().date()

    def now(self) -> datetime:
        return datetime.now()
