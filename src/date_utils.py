from datetime import UTC, date, datetime, timedelta
from database import Uptime
from typing import Sequence
from discord.ext.commands import CommandError

from number_utils import is_int

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
    
def parse_datetime_string(input: str) -> datetime:
    '''
    Converts a string to a datetime object.
    Supported datetime formats: "yyyy-MM-dd HH:mm", "dd-MM-yyyy HH:mm", "dd/MM/yyyy HH:mm", "HH:MM" (will use the current date).

    Args:
        input (str): The input time string

    Raises:
        commands.CommandError: If the input is not correctly formatted.

    Returns:
        datetime: The datetime object
    '''

    datetime_formats: list[str] = [
        '%Y-%m-%d %H:%M',
        '%d-%m-%Y %H:%M',
        '%d/%m/%Y %H:%M'
    ]

    for format in datetime_formats:
        try:
            time: datetime = datetime.strptime(input, format)
            return time
        except:
            pass
    
    time_formats: list[str] = [
        '%H:%M'
    ]

    now: datetime = datetime.now(UTC)

    for format in time_formats:
        try:
            time: datetime = datetime.strptime(input, format)
            time = time.replace(year=now.year, month=now.month, day=now.day)
            return time
        except:
            pass

    raise CommandError(f'Time `{input}` was not correctly formatted. To find the correct format, please use the `help` command, followed by the name of the command you are trying to use.')

def parse_timedelta_string(input: str) -> timedelta:
    '''
    Converts a string to a timedelta object.
    Support formats: HH:MM, or [num][unit]* where unit in {d, h, m}, 0 (for a zero-time interval)

    Args:
        input (str): The input time string

    Returns:
        timedelta: The timedelta object
    '''
    # Zero-time delta
    if input == '0':
        return timedelta(minutes=0)
    
    # HH:MM
    try:
        return datetime.strptime(input, '%H:%M') - datetime(1900, 1, 1)
    except:
        pass

    # [num][unit] where unit in {d, h, m}
    input = input.replace(' ', '').lower()
    units: list[str] = ['d', 'h', 'm']
    unit_values: dict[str, int] = {}
    num: str = ''
    for char in input:
        if is_int(char):
            num += char
        elif char in units and num and not char in unit_values:
            unit_values[char] = int(num)
            num = ''
        else:
            raise CommandError(message=f'Invalid argument: `{input}`.')
        
    days: int = unit_values['d'] if 'd' in unit_values else 0
    hours: int = unit_values['h'] if 'h' in unit_values else 0
    minutes: int = unit_values['m'] if 'm' in unit_values else 0

    return timedelta(days=days, hours=hours, minutes=minutes)