from typing import Any
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from main import Bot, get_config, increment_command_counter, Guild, Notification, OnlineNotification
import sys
sys.path.append('../')
from datetime import datetime, timedelta, UTC
from utils import is_int, is_admin

config = get_config()

ranks = ['Warbands', 'Amlodd', 'Hefin', 'Ithell', 'Trahaearn', 'Meilyr', 'Crwys',
         'Cadarn', 'Iorwerth', 'Cache', 'Sinkhole', 'Yews', 'Goebies', 'Merchant',
         'Spotlight', 'WildernessFlashEvents']

class Notifications(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(aliases=['rsnewschannel', 'newschannel'])
    @is_admin()
    async def rs3newschannel(self, ctx: commands.Context, channel=''):
        '''
        Changes the server's RS3 news channel. (Admin+)
        Arguments: channel
        If no channel is given, RS3 news messages will be disabled.
        '''
        increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'Required argument missing: `guild`.')

        guild = await Guild.get(ctx.guild.id)

        if not channel:
            if guild.rs3_news_channel_id:
                await guild.update(rs3_news_channel_id=None).apply()
                await ctx.send('RS3 news messages have been disabled for this server.')
                return
            else:
                raise commands.CommandError(message=f'Required argument missing: `channel`.')
        else:
            if ctx.message.channel_mentions:
                channel = ctx.message.channel_mentions[0]
            elif is_int(channel):
                id = channel
                channel = ctx.guild.get_channel(int(id))
                if not channel:
                    raise commands.CommandError(message=f'Could not find channel: `{id}`.')
            else:
                found = False
                for c in ctx.guild.text_channels:
                    if c.name.lower() == channel.lower():
                        channel = c
                        found = True
                        break
                if not found:
                    raise commands.CommandError(message=f'Could not find channel: `{channel}`.')
            
            if not isinstance(channel, discord.TextChannel):
                raise commands.CommandError(message=f'Could not find channel: `{channel}`.')
            
            await guild.update(rs3_news_channel_id=channel.id).apply()

            await ctx.send(f'The RS3 news channel has been set to {channel.mention}.')


    @commands.command(aliases=['07newschannel'])
    @is_admin()
    async def osrsnewschannel(self, ctx: commands.Context, channel=''):
        '''
        Changes the server's OSRS news channel. (Admin+)
        Arguments: channel
        If no channel is given, OSRS news messages will be disabled.
        '''
        increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'Required argument missing: `guild`.')

        guild = await Guild.get(ctx.guild.id)

        if not channel:
            if guild.osrs_news_channel_id:
                await guild.update(osrs_news_channel_id=None).apply()
                await ctx.send('OSRS news messages have been disabled for this server.')
                return
            else:
                raise commands.CommandError(message=f'Required argument missing: `channel`.')
        else:
            if ctx.message.channel_mentions:
                channel = ctx.message.channel_mentions[0]
            elif is_int(channel):
                id = channel
                channel = ctx.guild.get_channel(int(id))
                if not channel:
                    raise commands.CommandError(message=f'Could not find channel: `{id}`.')
            else:
                found = False
                for c in ctx.guild.text_channels:
                    if c.name.lower() == channel.lower():
                        channel = c
                        found = True
                        break
                if not found:
                    raise commands.CommandError(message=f'Could not find channel: `{channel}`.')
                
            if not isinstance(channel, discord.TextChannel):
                raise commands.CommandError(message=f'Could not find channel: `{channel}`.')
            
            await guild.update(osrs_news_channel_id=channel.id).apply()

            await ctx.send(f'The OSRS news channel has been set to {channel.mention}.')

    @commands.command(pass_context=True)
    @is_admin()
    async def rsnotify(self, ctx: commands.Context, channel=''):
        '''
        Changes server's RS notification channel. (Admin+)
        Arguments: channel.
        If no channel is given, notifications will no longer be sent.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise commands.CommandError(message=f'Required argument missing: `guild`.')

        if ctx.message.channel_mentions:
            channel = ctx.message.channel_mentions[0]
        elif channel:
            found = False
            for c in ctx.guild.text_channels:
                if channel.upper() in c.name.upper():
                    channel = c
                    found = True
                    break
            if not found:
                raise commands.CommandError(message=f'Could not find channel: `{channel}`.')
        else:
            guild = await Guild.get(ctx.guild.id)
            if guild.notification_channel_id:
                await guild.update(notification_channel_id=None).apply()
                await ctx.send(f'I will no longer send notifications in server **{ctx.guild.name}**.')
                return
            else:
                raise commands.CommandError(message=f'Required argument missing: `channel`.')
            
        if not isinstance(channel, discord.TextChannel):
            raise commands.CommandError(message=f'Could not find channel: `{channel}`.')

        permissions = discord.Permissions.none()
        colour = discord.Colour.default()
        role_names = []
        for role in ctx.guild.roles:
            role_names.append(role.name.upper())
        for rank in ranks:
            if not rank.upper() in role_names:
                try:
                    await ctx.guild.create_role(name=rank, permissions=permissions, colour=colour, hoist=False, mentionable=True)
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `create_roles`.')
        
        guild = await Guild.get(ctx.guild.id)
        await guild.update(notification_channel_id=channel.id).apply()
        
        await ctx.send(f'The notification channel for server **{ctx.guild.name}** has been changed to {channel.mention}.')

    @commands.command()
    @is_admin()
    async def addnotification(self, ctx: commands.Context, channel, time, interval, *message):
        '''
        Adds a custom notification. (Admin+)
        Format:
        channel: mention, id, or name
        time (UTC): "DD-MM-YYYY HH:MM", "DD/MM/YYYY HH:MM", "DD-MM HH:MM", "DD/MM HH:MM", HH:MM
        interval: HH:MM, [num][unit]* where unit in {d, h, m}, 0 (one time only notification)
        message: string
        '''
        increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise commands.CommandError(message=f'Required argument missing: `guild`.')

        guild = ctx.guild
        msg = ctx.message

        # Check given channel
        temp = None
        if channel:
            if msg.channel_mentions:
                temp = msg.channel_mentions[0]
            elif is_int(channel):
                temp = guild.get_channel(int(channel))
                if not temp:
                    for c in guild.text_channels:
                        if c.name.upper() == channel.upper():
                            temp = c
                            break
            else:
                for c in guild.text_channels:
                    if c.name.upper() == channel.upper():
                        temp = c
                        break
        if temp:
            channel = temp
        else:
            raise commands.CommandError(message=f'Could not find channel: `{channel}`.')

        # Handle input time
        input_time = time
        time = time.replace('/', '-')
        parts = time.split('-')
        if ' ' in parts[len(parts)-1]:
            temp = parts[len(parts)-1]
            parts = parts[:len(parts)-1]
            for part in temp.split(' '):
                parts.append(part.strip())
        if len(parts) == 1: # format: HH:MM
            parts = parts[0].split(':')
            if len(parts) != 2:
                await ctx.send(f'Time `{input_time}` was not correctly formatted. For the correct format, please use the `help addnotification` command.')
                return
            hours, minutes = parts[0], parts[1]
            if not is_int(hours):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 17.')
            hours = int(hours)
            if hours < 0 or hours > 23:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 18.')

            if not is_int(minutes):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 19.')
            minutes = int(minutes)
            if minutes < 0 or minutes > 59:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 20.')
            time = datetime.now(UTC)
            time = time.replace(microsecond=0, second=0, minute=minutes, hour=hours)
        elif len(parts) == 3: # format: DD-MM HH:MM
            day = parts[0]
            month = parts[1]
            time_of_day = parts[2]
            if not is_int(month):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 21.')
            month = int(month)
            if month < 1 or month > 12:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 22.')
            if not is_int(day):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 23.')
            day = int(day)
            year = datetime.now(UTC).year
            if month in [1, 3, 5, 7, 8, 10, 12] and (day < 1 or day > 31):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 24.')
            elif month in [4, 6, 9, 11] and (day < 1 or day > 30):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 25.')
            elif year % 4 == 0 and month == 2 and (day < 0 or day > 29):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 26.')
            elif year % 4 != 0 and month == 2 and (day < 0 or day > 28):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 27.')
            parts = time_of_day.split(':')
            if len(parts) != 2:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 28.')
            hours, minutes = parts[0], parts[1]
            if not is_int(hours):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 29.')
            hours = int(hours)
            if hours < 0 or hours > 23:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 30.')

            if not is_int(minutes):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 31.')
            minutes = int(minutes)
            if minutes < 0 or minutes > 59:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 32.')
            time = datetime.now(UTC)
            time = time.replace(microsecond=0, second=0, minute=minutes, hour=hours, day=day, month=month)
        elif len(parts) == 4:
            day = parts[0]
            month = parts[1]
            year = parts[2]
            time_of_day = parts[3]
            if not is_int(year):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 1.')
            year = int(year)
            if year < datetime.now(UTC).year or year > datetime.now(UTC).year+1:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 2.')
            if not is_int(month):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 3.')
            month = int(month)
            if month < 1 or month > 12:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 4.')
            if not is_int(day):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 5.')
            day = int(day)
            if month in [1, 3, 5, 7, 8, 10, 12] and (day < 1 or day > 31):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 6.')
            elif month in [4, 6, 9, 11] and (day < 1 or day > 30):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 7.')
            elif year % 4 == 0 and month == 2 and (day < 0 or day > 29):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 8.')
            elif year % 4 != 0 and month == 2 and (day < 0 or day > 28):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 9.')
            parts = time_of_day.split(':')
            if len(parts) != 2:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 10.')
            hours, minutes = parts[0], parts[1]
            if not is_int(hours):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 11.')
            hours = int(hours)
            if hours < 0 or hours > 23:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 12.')

            if not is_int(minutes):
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 13.')
            minutes = int(minutes)
            if minutes < 0 or minutes > 59:
                raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 14.')
            time = datetime.now(UTC)
            time = time.replace(microsecond=0, second=0, minute=minutes, hour=hours, day=day, month=month, year=year)
        else:
            raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 15.')
        if time < datetime.now(UTC):
            raise commands.CommandError(message=f'Invalid argument: `{time}`. Error ID: 16.')

        # Handle input time interval
        if interval == '0':
            interval = timedelta(minutes=0)
        elif ':' in interval: # format: HH:MM
            parts = interval.split(':')
            if len(parts) != 2:
                raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
            hours, minutes = parts[0], parts[1]
            if not is_int(hours):
                raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
            hours = int(hours)
            if hours < 0 or hours > 23:
                raise commands.CommandError(message=f'Invalid argument: `{interval}`.')

            if not is_int(minutes):
                raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
            minutes = int(minutes)
            if minutes < 0 or minutes > 59:
                raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
            interval = timedelta(hours=hours, minutes=minutes)
        else: # format: [num][unit] where unit in {d, h, m}
            temp = interval.replace(' ', '')
            units = ['d', 'h', 'm']
            input = []
            num = ''
            for char in temp:
                if not is_int(char) and not char.lower() in units:
                    raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
                elif is_int(char):
                    num += char
                elif char.lower() in units:
                    if not num:
                        raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
                    input.append((int(num), char.lower()))
                    num = ''
            days = 0
            hours = 0
            minutes = 0
            for i in input:
                num = i[0]
                unit = i[1]
                if unit == 'd':
                    days += num
                elif unit == 'h':
                    hours += num
                elif unit == 'm':
                    minutes += num
            if days*24*60 + hours*60 + minutes <= 0:
                raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
            elif days*24*60 + hours*60 + minutes > 60*24*366:
                raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
            interval = timedelta(days=days, hours=hours, minutes=minutes)

        if 0 < interval.total_seconds() < 900:
            raise commands.CommandError(message=f'Invalid argument: `{interval}`. Interval must be at least 15 minutes when set.')

        # Handle input message
        msg = ''
        for m in message:
            msg += m + ' '
        msg = msg.strip()
        if not msg:
            raise commands.CommandError(message=f'Invalid argument: `message`.')
        
        notifications = await Notification.query.where(Notification.guild_id==ctx.guild.id).order_by(Notification.notification_id.desc()).gino.all()
        id = 0
        if notifications:
            id = notifications[0].notification_id + 1
        await Notification.create(notification_id=id, guild_id=ctx.guild.id, channel_id=channel.id, time=time, interval=interval.total_seconds(), message=msg)

        await ctx.send(f'Notification added with id: `{id}`\n```channel:  {channel.id}\ntime:     {str(time)} UTC\ninterval: {int(interval.total_seconds())} (seconds)\nmessage:  {msg}```')

    @commands.command()
    async def notifications(self, ctx: commands.Context):
        '''
        Returns list of custom notifications for this server.
        '''
        increment_command_counter()

        notifications = await Notification.query.where(Notification.guild_id==ctx.guild.id).order_by(Notification.notification_id.asc()).gino.all()
        if not notifications:
            raise commands.CommandError(message=f'Error: this server does not have any custom notifications.')
        
        msg = ''
        for notification in notifications:
            msg += f'id:       {notification.notification_id}\nchannel:  {notification.channel_id}\ntime:     {notification.time} UTC\ninterval: {notification.interval} (seconds)\nmessage:  {notification.message}\n\n'
        msg = msg.strip()
        if len(msg) <= 1994:
            await ctx.send(f'```{msg}```')
        else:
            # https://stackoverflow.com/questions/13673060/split-string-into-strings-by-length
            chunks, chunk_size = len(msg), 1994 # msg at most 2000 chars, and we have 6 ` chars
            msgs = [msg[i:i+chunk_size] for i in range(0, chunks, chunk_size)]
            for msg in msgs:
                await ctx.send(f'```{msg}```')

    @commands.command()
    @is_admin()
    async def removenotification(self, ctx: commands.Context, id):
        '''
        Removes a custom notification by ID. (Admin+)
        To get the ID of the notification that you want to remove, use the command "notifications".
        '''
        increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'Required argument missing: `guild`.')

        if not id:
            raise commands.CommandError(message=f'Required argument missing: `id`.')
        if not is_int(id):
            raise commands.CommandError(message=f'Invalid argument: `{id}`. Must be an integer.')
        else:
            id = int(id)

        notification = await Notification.query.where(Notification.guild_id==ctx.guild.id).where(Notification.notification_id==id).gino.first()
        if not notification:
            raise commands.CommandError(message=f'Could not find custom notification: `{id}`.')
        
        await notification.delete()

        notifications = await Notification.query.where(Notification.guild_id==ctx.guild.id).order_by(Notification.notification_id.asc()).gino.all()
        if notifications:
            for i, notification in enumerate(notifications):
                await notification.update(notification_id=i).apply()

        await ctx.send(f'Removed custom notification: `{id}`')
    
    @commands.command(aliases=['updatenotification'])
    @is_admin()
    async def editnotification(self, ctx: commands.Context, id, key='message', *value):
        '''
        Update an existing notification. (Admin+)
        Key can be "channel", "time", "interval", or "message"
        Format:
        channel: mention, id, or name
        time (UTC): "DD-MM-YYYY HH:MM", "DD/MM/YYYY HH:MM", "DD-MM HH:MM", "DD/MM HH:MM", HH:MM
        interval: HH:MM, [num][unit]* where unit in {d, h, m}, 0 (one time only notification)
        message: string
        '''
        increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'Required argument missing: `guild`.')

        if not id:
            raise commands.CommandError(message=f'Required argument missing: `id`.')
        if not is_int(id):
            raise commands.CommandError(message=f'Invalid argument: `{id}`. ID must be an integer.')
        else:
            id = int(id)
        
        if not key in ['channel', 'time', 'interval', 'message']:
            raise commands.CommandError(message=f'Invalid argument: `{key}`. Key must be channel, time, interval, or message.')

        if not value:
            raise commands.CommandError(message=f'Required argument missing: `value`.')
        value = ' '.join(value).strip()
        if not value:
            raise commands.CommandError(message=f'Required argument missing: `value`.')

        notification = await Notification.query.where(Notification.guild_id==ctx.guild.id).where(Notification.notification_id==id).gino.first()
        if not notification:
            raise commands.CommandError(message=f'Could not find custom notification: `{id}`.')
        
        if key == 'channel':
            if ctx.message.channel_mentions:
                temp = ctx.message.channel_mentions[0]
            elif is_int(value):
                temp = ctx.guild.get_channel(int(value))
                if not temp:
                    for c in ctx.guild.text_channels:
                        if c.name.upper() == value.upper():
                            temp = c
                            break
            else:
                for c in ctx.guild.text_channels:
                    if c.name.upper() == value.upper():
                        temp = c
                        break
            if temp:
                channel = temp
            else:
                raise commands.CommandError(message=f'Could not find channel: `{value}`.')
            await notification.update(channel_id=channel.id).apply()
        
        elif key == 'time':
            time = value
            input_time = time
            time = time.replace('/', '-')
            parts = time.split('-')
            if ' ' in parts[len(parts)-1]:
                temp = parts[len(parts)-1]
                parts = parts[:len(parts)-1]
                for part in temp.split(' '):
                    parts.append(part)
            if len(parts) == 1: # format: HH:MM
                parts = parts[0].split(':')
                if len(parts) != 2:
                    await ctx.send(f'Time `{input_time}` was not correctly formatted. For the correct format, please use the `help addnotification` command.')
                    return
                hours, minutes = parts[0], parts[1]
                if not is_int(hours):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                hours = int(hours)
                if hours < 0 or hours > 23:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')

                if not is_int(minutes):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                minutes = int(minutes)
                if minutes < 0 or minutes > 59:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                time = datetime.now(UTC)
                time = time.replace(microsecond=0, second=0, minute=minutes, hour=hours)
            elif len(parts) == 3: # format: DD-MM HH:MM
                day = parts[0]
                month = parts[1]
                time_of_day = parts[2]
                if not is_int(month):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                month = int(month)
                if month < 1 or month > 12:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                if not is_int(day):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                day = int(day)
                year = datetime.now(UTC).year
                if month in [1, 3, 5, 7, 8, 10, 12] and (day < 1 or day > 31):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                elif month in [4, 6, 9, 11] and (day < 1 or day > 30):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                elif year % 4 == 0 and month == 2 and (day < 0 or day > 29):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                elif year % 4 != 0 and month == 2 and (day < 0 or day > 28):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                parts = time_of_day.split(':')
                if len(parts) != 2:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                hours, minutes = parts[0], parts[1]
                if not is_int(hours):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                hours = int(hours)
                if hours < 0 or hours > 23:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')

                if not is_int(minutes):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                minutes = int(minutes)
                if minutes < 0 or minutes > 59:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                time = datetime.now(UTC)
                time = time.replace(microsecond=0, second=0, minute=minutes, hour=hours, day=day, month=month)
            elif len(parts) == 4:
                day = parts[0]
                month = parts[1]
                year = parts[2]
                time_of_day = parts[3]
                if not is_int(year):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                year = int(year)
                if year < datetime.now(UTC).year or year > datetime.now(UTC).year+1:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                if not is_int(month):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                month = int(month)
                if month < 1 or month > 12:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                if not is_int(day):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                day = int(day)
                if month in [1, 3, 5, 7, 8, 10, 12] and (day < 1 or day > 31):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                elif month in [4, 6, 9, 11] and (day < 1 or day > 30):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                elif year % 4 == 0 and month == 2 and (day < 0 or day > 29):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                elif year % 4 != 0 and month == 2 and (day < 0 or day > 28):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                parts = time_of_day.split(':')
                if len(parts) != 2:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                hours, minutes = parts[0], parts[1]
                if not is_int(hours):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                hours = int(hours)
                if hours < 0 or hours > 23:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')

                if not is_int(minutes):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                minutes = int(minutes)
                if minutes < 0 or minutes > 59:
                    raise commands.CommandError(message=f'Invalid argument: `{time}`.')
                time = datetime.now(UTC)
                time = time.replace(microsecond=0, second=0, minute=minutes, hour=hours, day=day, month=month, year=year)
            else:
                raise commands.CommandError(message=f'Invalid argument: `{time}`.')
            if time < datetime.now(UTC):
                raise commands.CommandError(message=f'Invalid argument: `{time}`.')

            await notification.update(time=time).apply()
        
        elif key == 'interval':
            interval = value
            temp = interval.replace(' ', '')
            units = ['d', 'h', 'm']
            input = []
            num = ''
            for char in temp:
                if not is_int(char) and not char.lower() in units:
                    raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
                elif is_int(char):
                    num += char
                elif char.lower() in units:
                    if not num:
                        raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
                    input.append((int(num), char.lower()))
                    num = ''
            days = 0
            hours = 0
            minutes = 0
            for i in input:
                num = i[0]
                unit = i[1]
                if unit == 'd':
                    days += num
                elif unit == 'h':
                    hours += num
                elif unit == 'm':
                    minutes += num
            if days*24*60 + hours*60 + minutes <= 0:
                raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
            elif days*24*60 + hours*60 + minutes > 60*24*366:
                raise commands.CommandError(message=f'Invalid argument: `{interval}`.')
            interval = timedelta(days=days, hours=hours, minutes=minutes)
            interval = interval.total_seconds()

            await notification.update(interval=interval).apply()
        
        else:
            await notification.update(message=value).apply()
        
        await ctx.send(f'Notification edited with id: `{id}`\n```channel:  {notification.channel_id}\ntime:     {notification.time} UTC\ninterval: {notification.interval} (seconds)\nmessage:  {notification.message}```')

    @commands.command()
    async def online(self, ctx: commands.Context, *member):
        '''
        Notify next time a user comes online.
        Arguments: member (mention, id, name), (optional: int type [1-4])
        Type 1: (default) notify when status changes to online
        Type 2: notify when status changes to anything but offline
        Type 3: notify when status changes to idle or online (i.e. type 2 excluding dnd)
        Type 4: notify when member goes offline
        Type 1-3 also trigger when the member sends a message
        '''
        increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'Required argument missing: `guild`.')
        
        if not member:
            raise commands.CommandError(message=f'Required argument missing: `member`.')
        type = 1
        potential_type = member[len(member) - 1]
        if is_int(potential_type):
            if 1 <= int(potential_type) <= 4:
                type = int(potential_type)
                member = member[0:len(member) - 1]

        member_mentions = [mention for mention in ctx.message.mentions if isinstance(mention, discord.Member)]
        if member_mentions:
            member = member_mentions[0]
        else:
            name = ""
            for m in member:
                name += m + " "
            name = name.strip()

            found = False
            if is_int(name):
                potential_id = int(name)
                for m in ctx.guild.members:
                    if m.id == potential_id:
                        found = True
                        member = m
                        break
            if not found:
                for m in ctx.guild.members:
                    if m.display_name.upper().replace(" ", "") == name.upper().replace(" ", ""):
                        found = True
                        member = m
                        break
            if not found:
                for m in ctx.guild.members:
                    if name.upper().replace(" ", "") in m.display_name.upper().replace(" ", ""):
                        found = True
                        member = m
                        break
            if not found:
                raise commands.CommandError(message=f'Could not find member: `{name}`.')
        
        if not isinstance(member, discord.Member):
            raise commands.CommandError(message=f'Could not find member.')
        
        members = await ctx.guild.query_members(user_ids=[member.id], presences=True)
        member = members[0]

        if type in [1,2,3] and str(member.status) == 'online':
            raise commands.CommandError(message=f'Error: `{member.display_name}` is already online.')
        elif type in [2,3] and str(member.status) == 'idle':
            raise commands.CommandError(message=f'Error: `{member.display_name}` is already online.')
        elif type == 2 and str(member.status) == 'dnd':
            raise commands.CommandError(message=f'Error: `{member.display_name}` is already online.')
        elif type == 4 and str(member.status) == 'offline':
            raise commands.CommandError(message=f'Error: `{member.display_name}` is already offline.')
        
        online_notification = await OnlineNotification.query.where(OnlineNotification.guild_id==ctx.guild.id).where(OnlineNotification.author_id==ctx.author.id).where(OnlineNotification.member_id==member.id).gino.first()
        if online_notification:
            await online_notification.delete()
            await ctx.send(f'You will no longer be notified of `{member.display_name}`\'s status.')
        else:
            await OnlineNotification.create(guild_id=ctx.guild.id, author_id=ctx.author.id, member_id=member.id, channel_id=ctx.message.channel.id, type=type)
            if type in [1,2,3]:
                await ctx.send(f'You will be notified when `{member.display_name}` is online.')
            else:
                await ctx.send(f'You will be notified when `{member.display_name}` is offline.')

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        '''
        Notify users of status updates.
        '''
        if before.status != after.status:
            try:
                online_notification = await OnlineNotification.query.where(OnlineNotification.guild_id==after.guild.id).where(OnlineNotification.member_id==after.id).gino.first()
            except:
                return
            if not online_notification:
                return
            if online_notification.type in [1,2,3] and str(after.status) == 'online':
                try:
                    channel = discord.utils.get(after.guild.channels, id=online_notification.channel_id)
                    user = discord.utils.get(after.guild.members, id=online_notification.author_id)
                    await channel.send(f'`{after.display_name}` is online! {user.mention}')
                except:
                    pass
            elif online_notification.type in [2,3] and str(after.status) == 'idle':
                try:
                    channel = discord.utils.get(after.guild.channels, id=online_notification.channel_id)
                    user = discord.utils.get(after.guild.members, id=online_notification.author_id)
                    await channel.send(f'`{after.display_name}` is online! {user.mention}')
                except:
                    pass
            elif online_notification.type == 2 and str(after.status) == 'dnd':
                try:
                    channel = discord.utils.get(after.guild.channels, id=online_notification.channel_id)
                    user = discord.utils.get(after.guild.members, id=online_notification.author_id)
                    await channel.send(f'`{after.display_name}` is online! {user.mention}')
                except:
                    pass
            elif online_notification.type == 4 and str(after.status) == 'offline':
                try:
                    channel = discord.utils.get(after.guild.channels, id=online_notification.channel_id)
                    user = discord.utils.get(after.guild.members, id=online_notification.author_id)
                    await channel.send(f'`{after.display_name}` is offline! {user.mention}')
                except:
                    pass
            else:
                return

            await online_notification.delete()
    
    @commands.Cog.listener()
    async def on_message(self, message):
        '''
        Notify of online status on activity.
        '''
        if message.guild is None:
            return
        try:
            online_notification = await OnlineNotification.query.where(OnlineNotification.guild_id==message.guild.id).where(OnlineNotification.member_id==message.author.id).gino.first()
        except:
            return
        if online_notification:
            if online_notification.type in [1,2,3]:
                try:
                    channel = discord.utils.get(message.guild.channels, id=online_notification.channel_id)
                    user = discord.utils.get(message.guild.members, id=online_notification.author_id)
                    await channel.send(f'`{message.author.display_name}` is online! {user.mention}')
                except:
                    pass
                await online_notification.delete()

async def setup(bot: Bot):
    await bot.add_cog(Notifications(bot))
