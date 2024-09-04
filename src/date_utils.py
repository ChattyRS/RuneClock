from datetime import UTC, date, datetime, timedelta
from database import Uptime
from typing import Sequence

months: list[str] = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

'''
Function to convert timedelta to a string of the form:
x day(s), x hour(s), x minute(s), x second(s)
'''
def timedelta_to_string(time: timedelta) -> str:
    '''
    Function to convert timedelta to a string of the form:
    x day(s), x hour(s), x minute(s), x second(s)

    Args:
        time (timedelta): The timedelta to convert

    Returns:
        str: The formatted timedelta
    '''
    postfix: str = ''
    if time < timedelta(seconds=0):
        time = -time
        postfix = ' ago'
    seconds: int = time.seconds
    days: int = time.days
    hours: int = seconds // 3600
    seconds -= hours * 3600
    minutes: int = seconds // 60
    seconds -= minutes * 60
    time_str: str = ""
    if days != 0:
        time_str += str(days) + " day"
        if days != 1:
            time_str += "s"
    if hours != 0:
        if days != 0:
            time_str += ", "
            if minutes == 0 and seconds == 0:
                time_str += "and "
        time_str += str(hours) + " hour"
        if hours != 1:
            time_str += "s"
    if minutes != 0:
        if days != 0 or hours != 0:
            time_str += ", "
            if seconds == 0:
                time_str += "and "
        time_str += str(minutes) + " minute"
        if minutes != 1:
            time_str += "s"
    if seconds != 0:
        if days != 0 or hours != 0 or minutes != 0:
            time_str += ", and "
        time_str += str(seconds) + " second"
        if seconds != 1:
            time_str += "s"
    return f'{time_str}{postfix}'

def uptime_fraction(events: Sequence[Uptime], year: int | None = None, month: int | None = None, day: int | None = None) -> float:
    '''
    Calculate the fraction of time that the bot was up from a sequence of uptime records.

    Args:
        events (Sequence[Uptime]): Sequence of uptime sequence
        year (int, optional): The year during which to measure the uptime (optional). Defaults to None.
        month (int, optional): The month during which to measure the uptime (optional). Defaults to None.
        day (int, optional): The day during which to measure the uptime (optional). Defaults to None.

    Returns:
        float: The fraction of time during which the bot was up in the given time period
    '''
    if day and month and year:
        today: date = date(year, month, day)
        if not any(event.time.date() == today for event in events):
            return 0
        elapsed = timedelta(hours=24)
        up = timedelta(seconds=0)
        start_time: datetime = datetime.now(UTC).replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
        for i, event in enumerate(events):
            if event.time.year == year and event.time.month == month and event.time.day == day:
                if event.status == 'started':
                    start_time = event.time
                elif event.status == 'running':
                    up += event.time - start_time
            elif event.time > start_time:
                last_event: Uptime = events[i-1]
                elapsed: timedelta = last_event.time - datetime.now(UTC).replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
                break
            if i == len(events) - 1:
                elapsed = event.time - datetime.now(UTC).replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
        return up.total_seconds() / elapsed.total_seconds()
    elif year and month:
        start: datetime | None = None
        end: datetime | None = None
        for i, event in enumerate(events):
            if event.time.year == year and event.time.month == month:
                if not start:
                    start = event.time
                end = event.time
            elif start and end:
                break
        percentages: list[float] = []
        if start and end:
            for day in range(start.day, end.day+1):
                percentages.append(uptime_fraction(events, year=year, month=month, day=day))
        return sum(percentages) / len(percentages)
    elif year:
        months: list[int] = []
        for i, event in enumerate(events):
            if event.time.year == year:
                if not event.time.month in months:
                    months.append(event.time.month)
        percentages = []
        for month in months:
            percentages.append(uptime_fraction(events, year=year, month=month))
        return sum(percentages) / len(percentages)
    else:
        years: list[int] = []
        for i, event in enumerate(events):
            if not event.time.year in years:
                years.append(event.time.year)
        percentages = []
        for year in years:
            percentages.append(uptime_fraction(events, year=year))
        return sum(percentages) / len(percentages)