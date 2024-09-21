import discord
from discord.ext import commands
from discord.ext.commands import Cog
import asyncio
from bot import Bot
from database import User
from datetime import datetime, timedelta, UTC
from date_utils import timedelta_to_string, string_to_timezone
import pytz
from number_utils import is_int
from pytz.tzinfo import StaticTzInfo, DstTzInfo

class Timer(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @commands.command(pass_context=True, aliases=['reminder', 'remind', 'remindme'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def timer(self, ctx: commands.Context, time: str = '', unit: str = 'm', *, msg: str | None) -> None:
        '''
        Lets the user set a timer.
        Arguments: time, unit (optional, default m), message (optional).
        Constraints: time can range from 1 s to 24 h. Unit can be s, m, h.
        Please note that timers will be lost if the bot is restarted or goes down unexpectedly.
        Don't forget to surround your inputs with "quotation marks" if they contains spaces.
        '''
        self.bot.increment_command_counter()

        if not time:
            raise commands.CommandError(message=f'Required argument missing: `time`.')
        count: int = time.count(':')
        if count:
            if count == 1:
                index: int = time.index(':')
                h: str = time[:index]
                m: str = time[index+1:]
                if not is_int(h) or not is_int(m):
                    raise commands.CommandError(message=f'Invalid argument: time `{time}`.')
                else:
                    time_seconds = int(h) * 3600 + int(m) * 60
                    if time_seconds % 3600 == 0:
                        unit = 'hours'
                    else:
                        unit = 'minutes'
            elif count == 2:
                index = time.index(':')
                h = time[:index]
                time = time[index+1:]
                index = time.index(':')
                m = time[:index]
                s: str = time[index+1:]
                if not is_int(h) or not is_int(m) or not is_int(s):
                    raise commands.CommandError(message=f'Invalid argument: time `{time}`.')
                else:
                    time_seconds = int(h) * 3600 + int(m) * 60 + int(s)
                    if time_seconds % 60 == 0:
                        unit = 'minutes'
                    elif time_seconds % 3600 == 0:
                        unit = 'hours'
                    else:
                        unit = 'seconds'
        elif is_int(time):
            time_seconds = int(time)
        else:
            raise commands.CommandError(message=f'Invalid argument: time `{time}`.')
        if not count:
            if unit:
                if 'S' in unit.upper():
                    unit = 'seconds'
                elif 'M' in unit.upper():
                    unit = 'minutes'
                    time_seconds *= 60
                elif 'H' in unit.upper():
                    unit = 'hours'
                    time_seconds *= 3600
            else:
                unit = 'minutes'
                time_seconds *= 60

        if time_seconds < 1 or time_seconds > 86400:
            raise commands.CommandError(message=f'Invalid argument: time `{time}`.')

        time_str: str = timedelta_to_string(timedelta(seconds=time_seconds))

        await ctx.send(f'You have set a timer for **{time_str}**.')

        await asyncio.sleep(time_seconds)

        await ctx.send(f'{ctx.author.mention} {msg if msg else "It's time!"}')

    @commands.command(aliases=['timezone'])
    async def tz(self, ctx: commands.Context, timezone: str = 'UTC') -> None:
        '''
        Check the time in a given timezone.
        '''
        self.bot.increment_command_counter()

        timezone = string_to_timezone(timezone)

        tz: pytz._UTCclass | StaticTzInfo | DstTzInfo = pytz.timezone(timezone)
        time: datetime = datetime.now(tz)

        time_str: str = time.strftime('%H:%M')

        await ctx.send(f'{timezone} time: `{time_str}`.')

    @commands.command()
    async def worldtime(self, ctx: commands.Context, *time) -> None:
        '''
        Convert a given time in UTC to several timezones across the world.
        '''
        increment_command_counter()

        input = ' '.join(time).upper()
        time = input

        if not time:
            raise commands.CommandError(message=f'Required argument missing: `time`.')

        # Format H(:MM) AM/PM
        am_pm_offset = timedelta(0)
        if 'AM' in time or 'PM' in time:
            if 'PM' in time:
                am_pm_offset = timedelta(hours=12)
            time = time.replace('AM', '').replace('PM', '').replace(' ', '')

        # Format: HH:MM
        if ':' in time:
            hours, minutes = time.split(':')
            if not is_int(hours) or not is_int(minutes):
                raise commands.CommandError(message=f'Invalid argument: time `{time}`.')
            hours, minutes = int(hours), int(minutes)
        else:
            hours, minutes = time, 0
            if not is_int(hours):
                raise commands.CommandError(message=f'Invalid argument: time `{time}`.')
            hours = int(hours)
        
        t_0 = datetime.now(UTC).replace(microsecond=0, second=0, minute=minutes, hour=hours)
        t_0 += am_pm_offset
        
        msg = []

        # US/Pacific = MST, US/Central = EST
        timezones = ['US/Pacific', 'US/Central', 'US/Eastern', 'UTC', 'Europe/London', 'CET', 'Australia/ACT']

        user = await User.get(ctx.author.id)
        if user:
            if user.timezone:
                if not user.timezone in timezones:
                    timezones.append(user.timezone)

        for timezone_name in timezones:
            timezone = pytz.timezone(timezone_name)
            t_x = t_0 + timezone.utcoffset(t_0)
            time_str = t_x.strftime('%H:%M')
            msg.append([t_x, f'{time_str} {timezone_name}'])
        
        msg = sorted(msg, key=lambda x: x[0])
        msg = '\n'.join([x[1] for x in msg])
        
        embed = discord.Embed(title=f'{input} UTC', colour=0x00b2ff, timestamp=datetime.now(UTC), description=msg)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        await ctx.send(embed=embed)
    
    @commands.command()
    async def settimezone(self, ctx: commands.Context, *tz_or_loc):
        '''
        Set your personal timezone.
        This timezone will be shown (among others) when you use the `worldtime` command.
        '''
        increment_command_counter()

        input = ' '.join(tz_or_loc).upper()

        if not input:
            timezone = None
        else:
            timezone = string_to_timezone(input)

        if timezone:
            tz = pytz.timezone(timezone)
            time = datetime.now(tz)
            time_str = time.strftime('%H:%M')

        user = await User.get(ctx.author.id)
        if user:
            await user.update(timezone=timezone).apply()
        else:
            await User.create(id=ctx.author.id, timezone=timezone)
        
        if timezone:
            await ctx.send(f'{ctx.author.mention} your timezone has been set to `{timezone}` ({time_str}).')
        else:
            await ctx.send(f'{ctx.author.mention} your timezone has been removed.')


async def setup(bot: Bot) -> None:
    await bot.add_cog(Timer(bot))
