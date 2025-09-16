import calendar
import datetime as dt
from zoneinfo import ZoneInfo


def last_day_of_month(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def anchor_day_in_month(y: int, m: int, anchor_day: int) -> int:
    return min(int(anchor_day), last_day_of_month(y, m))


def local_today(tz: str) -> dt.date:
    return dt.datetime.now(ZoneInfo(tz)).date()


def current_period_end(tz: str, anchor_day: int, today: dt.date | None = None) -> dt.date:
    d = today or local_today(tz)
    day = anchor_day_in_month(d.year, d.month, anchor_day)
    return dt.date(d.year, d.month, day)


def next_period_end(tz: str, anchor_day: int, from_date: dt.date | None = None) -> dt.date:
    d = (from_date or local_today(tz))
    # add one month safely
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    day = anchor_day_in_month(year, month, anchor_day)
    return dt.date(year, month, day)


def local_date_for_process_utc(process_date_utc: dt.date | None, tz: str) -> dt.date:
    """Given a process date in UTC, return the local date in the user's timezone.
    If process_date_utc is None, returns today's date in the user's timezone.
    """
    if process_date_utc is None:
        return local_today(tz)
    # Interpret process_date_utc at UTC midnight, convert to tz, then take .date()
    midnight_utc = dt.datetime(process_date_utc.year, process_date_utc.month, process_date_utc.day, tzinfo=ZoneInfo("UTC"))
    return midnight_utc.astimezone(ZoneInfo(tz)).date()

