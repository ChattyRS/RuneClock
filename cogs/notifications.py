import logging
from typing import Sequence
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from sqlalchemy import select
from src.bot import Bot
from src.database import Guild, Notification, OnlineNotification
from datetime import datetime, timedelta, UTC
from src.database_utils import get_db_guild
from src.discord_utils import find_text_channel, get_guild_text_channel, get_text_channel, get_text_channel_by_name, send_code_block_over_multiple_messages
from src.message_queue import QueueMessage
from src.number_utils import is_int
from src.checks import is_admin
from src.runescape_utils import dnd_names
from discord.abc import GuildChannel
from src.date_utils import parse_datetime_string, parse_timedelta_string

class Notifications(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    def cog_load(self) -> None:
        '''
        Starts background tasks when the cog is loaded.
        '''
        self.bot.loop.create_task(self.role_setup())

    async def role_setup(self) -> None:
        '''
        Sets up message and reactions for role management if no message is sent in the channel yet
        Adds messages to cache to track reactions
        '''
        print(f'Initializing role management...')
        logging.info('Initializing role management...')

        guilds: Sequence[Guild]
        async with self.bot.async_session() as session:
            guilds = (await session.execute(select(Guild).where(Guild.role_channel_id.isnot(None)))).scalars().all()

        channels: list[discord.TextChannel] = []
        for db_guild in guilds:
            channel: discord.TextChannel | None = find_text_channel(self.bot, db_guild.role_channel_id)
            if channel:
                channels.append(channel)

        if not channels:
            msg: str = f'Sorry, I was unable to retrieve any role management channels. Role management is down.'
            print(msg)
            print('-' * 10)
            logging.critical(msg)
            logChannel: discord.TextChannel = get_text_channel(self.bot, self.bot.config['testChannel'])
            self.bot.queue_message(QueueMessage(logChannel, msg))
            return
            
        msg = "React to this message with any of the following emoji to be added to the corresponding role for notifications:\n\n"
        notif_emojis: list[discord.Emoji] = []
        for r in dnd_names:
            emoji_id: int = self.bot.config[f'{r.lower()}EmojiID']
            emoji: discord.Emoji | None = self.bot.get_emoji(emoji_id)
            if emoji:
                notif_emojis.append(emoji)
                msg += str(emoji) + ' ' + r + '\n'
        msg += "\nIf you wish to stop receiving notifications, simply remove your reaction. If your reaction isn't there anymore, then you can add a new one and remove it."
        for c in channels:
            try:
                messages = 0
                async for message in c.history(limit=1):
                    messages += 1
                if not messages:
                    message: discord.Message = await c.send(msg)
                    try:
                        for emoji in notif_emojis:
                            await message.add_reaction(emoji)
                    except Exception as e:
                        print(f'Exception: {e}')
            except discord.Forbidden:
                continue

        msg = f'Role management ready'
        print(msg)
        print('-' * 10)
        logging.info(msg)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        '''
        Function to add handle on reactions
        '''
        channel: discord.TextChannel | None = find_text_channel(self.bot, payload.channel_id)
        if not channel:
            return

        user: discord.Member = await channel.guild.fetch_member(payload.user_id)
        if user.bot:
            return

        guild: Guild = await get_db_guild(self.bot.async_session, channel.guild)
        if guild.role_channel_id != channel.id:
            return
        
        emoji: discord.PartialEmoji = payload.emoji
        role_name: str = emoji.name

        if role_name in dnd_names:
            role: discord.Role | None = discord.utils.get(channel.guild.roles, name=role_name)
        if not role:
            return
        
        try:
            await user.add_roles(role)
        except discord.Forbidden:
            pass

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        '''
        Function to remove roles on reactions
        '''
        channel: discord.TextChannel | None = find_text_channel(self.bot, payload.channel_id)
        if not channel:
            return
        
        user: discord.Member = await channel.guild.fetch_member(payload.user_id)
        if user.bot:
            return
        
        guild: Guild = await get_db_guild(self.bot.async_session, channel.guild)
        if guild.role_channel_id != channel.id:
            return

        emoji: discord.PartialEmoji = payload.emoji
        role_name: str = emoji.name
        
        if role_name in dnd_names:
            role: discord.Role | None = discord.utils.get(channel.guild.roles, name=role_name)
        if not role:
            return
        
        try:
            await user.remove_roles(role)
        except discord.Forbidden:
            return

    @commands.command(aliases=['rsnewschannel', 'newschannel'])
    @is_admin()
    async def rs3newschannel(self, ctx: commands.Context, *, channel: GuildChannel | None) -> None:
        '''
        Changes the server's RS3 news channel. (Admin+)
        Arguments: channel
        If no channel is given, RS3 news messages will be disabled.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used in a server.')
        
        async with self.bot.async_session() as session:
            guild: Guild = await get_db_guild(self.bot.async_session, ctx.guild, session)

            if not channel and not guild.rs3_news_channel_id:
                raise commands.CommandError(message=f'Required argument missing: `channel`.')
            elif not channel:
                guild.rs3_news_channel_id = None
                await session.commit()
                await ctx.send('RS3 news messages have been disabled for this server.')
                return
            
            guild.rs3_news_channel_id = channel.id
            await session.commit()

            await ctx.send(f'The RS3 news channel has been set to {channel.mention}.')


    @commands.command(aliases=['07newschannel'])
    @is_admin()
    async def osrsnewschannel(self, ctx: commands.Context, *, channel: GuildChannel | None) -> None:
        '''
        Changes the server's OSRS news channel. (Admin+)
        Arguments: channel
        If no channel is given, OSRS news messages will be disabled.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used in a server.')
        
        async with self.bot.async_session() as session:
            guild: Guild = await get_db_guild(self.bot.async_session, ctx.guild, session)

            if not channel and not guild.osrs_news_channel_id:
                raise commands.CommandError(message=f'Required argument missing: `channel`.')
            elif not channel:
                guild.osrs_news_channel_id = None
                await session.commit()
                await ctx.send(content='OSRS news messages have been disabled for this server.')
                return
            
            guild.osrs_news_channel_id = channel.id
            await session.commit()

            await ctx.send(f'The OSRS news channel has been set to {channel.mention}.')

    @commands.command(pass_context=True)
    @is_admin()
    async def rsnotify(self, ctx: commands.Context, *, channel: GuildChannel | None) -> None:
        '''
        Changes server's RS notification channel. (Admin+)
        Arguments: channel.
        If no channel is given, notifications will no longer be sent.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used in a server.')
        
        if channel:
            permissions: discord.Permissions = discord.Permissions.none()
            colour: discord.Colour = discord.Colour.default()
            for rank in [dnd_name for dnd_name in dnd_names if not dnd_name.upper() in [role.name.upper() for role in ctx.guild.roles]]:
                try:
                    await ctx.guild.create_role(name=rank, permissions=permissions, colour=colour, hoist=False, mentionable=True)
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `create_roles`.')
        
        async with self.bot.async_session() as session:
            guild: Guild = await get_db_guild(self.bot.async_session, ctx.guild, session)

            if not channel and not guild.notification_channel_id:
                raise commands.CommandError(message=f'Required argument missing: `channel`.')
            elif not channel:
                guild.notification_channel_id = None
                await session.commit()
                await ctx.send(content='I will no longer send notifications in server **{ctx.guild.name}**.')
                return

            guild.notification_channel_id = channel.id
            await session.commit()
        
        await ctx.send(f'The notification channel for server **{ctx.guild.name}** has been changed to {channel.mention}.')

    @commands.command()
    @is_admin()
    async def addnotification(self, ctx: commands.Context, channel: GuildChannel | str | int | None, time: datetime | str | None, interval: timedelta | str | None, *, message: str) -> None:
        '''
        Adds a custom notification. (Admin+)
        Format:
        channel: mention, id, or name
        time (UTC): "DD-MM-YYYY HH:MM", "DD/MM/YYYY HH:MM", "DD-MM HH:MM", "DD/MM HH:MM", HH:MM
        interval: HH:MM, [num][unit]* where unit in {d, h, m}, 0 (one time only notification)
        message: string
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used in a server.')
        if not channel:
            raise commands.CommandError(message=f'Required argument missing: `channel`.')
        if not time:
            raise commands.CommandError(message=f'Required argument missing: `time`.')
        if not interval:
            raise commands.CommandError(message=f'Required argument missing: `interval`.')
        if not message:
            raise commands.CommandError(message=f'Required argument missing: `message`.')

        # Check given channel
        if channel and not isinstance(channel, GuildChannel):
            if ctx.message.channel_mentions and isinstance(ctx.message.channel_mentions[0], GuildChannel):
                channel = ctx.message.channel_mentions[0]
            elif is_int(channel):
                channel_by_id = ctx.guild.get_channel(int(channel))
                channel = channel_by_id if channel_by_id else str(channel)
            if isinstance(channel, str):
                channel = get_text_channel_by_name(ctx.guild, channel)
        if not isinstance(channel, GuildChannel):
            raise commands.CommandError(f'Could not find channel.')

        # Handle input time
        time = parse_datetime_string(time) if isinstance(time, str) else time
        time = time.replace(tzinfo=UTC)
        if time < datetime.now(UTC):
            raise commands.CommandError(f'Invalid argument: `{time}`. Time cannot be in the past.')

        # Handle input time interval
        interval = parse_timedelta_string(interval) if isinstance(interval, str) else interval
        if (interval.days if interval.days else 0) * 24 * 60 * 60 + (interval.seconds if interval.seconds else 0) > 366 * 24 * 60 * 60:
            raise commands.CommandError(f'Invalid argument: `{interval}`. Interval cannot exceed 1 year.')
        if 0 < interval.total_seconds() < 900:
            raise commands.CommandError(f'Invalid argument: `{interval}`. Interval must be at least 15 minutes when set.')
        
        async with self.bot.async_session() as session:
            id: int | None = (await session.execute(select(Notification.notification_id).where(Notification.guild_id == ctx.guild.id).order_by(Notification.notification_id.desc()))).scalar()
            id = id+1 if id is not None else 0
            session.add(Notification(notification_id=id, guild_id=ctx.guild.id, channel_id=channel.id, time=time, interval=round(interval.total_seconds()), message=message))
            await session.commit()

        await ctx.send(f'Notification added with id: `{id}`\n```channel:  {channel.id}\ntime:     {str(time)} UTC\ninterval: {int(interval.total_seconds())} (seconds)\nmessage:  {message}```')

    @commands.command()
    async def notifications(self, ctx: commands.Context) -> None:
        '''
        Returns list of custom notifications for this server.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used in a server.')

        async with self.bot.async_session() as session:
            notifications: Sequence[Notification] = (await session.execute(select(Notification).where(Notification.guild_id == ctx.guild.id).order_by(Notification.notification_id.desc()))).scalars().all()

        if not notifications:
            raise commands.CommandError(message=f'Error: this server does not have any custom notifications.')
        
        msg: str = '\n\n'.join([f'id:       {n.notification_id}\nchannel:  {n.channel_id}\ntime:     {n.time} UTC\ninterval: {n.interval} (seconds)\nmessage:  {n.message}' for n in notifications])
        await send_code_block_over_multiple_messages(ctx, msg)

    @commands.command()
    @is_admin()
    async def removenotification(self, ctx: commands.Context, id: str | int) -> None:
        '''
        Removes a custom notification by ID. (Admin+)
        To get the ID of the notification that you want to remove, use the command "notifications".
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used in a server.')

        if not id:
            raise commands.CommandError(message=f'Required argument missing: `id`.')
        if not is_int(id):
            raise commands.CommandError(message=f'Invalid argument: `{id}`. Must be an integer.')
        else:
            id = int(id)

        async with self.bot.async_session() as session:
            notifications: list[Notification] = [n for n in (await session.execute(select(Notification).where(Notification.guild_id == ctx.guild.id).order_by(Notification.notification_id.asc()))).scalars().all()]
            notification: list[Notification] | Notification = [n for n in notifications if n.notification_id == id]
            if not notification:
                raise commands.CommandError(message=f'Could not find custom notification: `{id}`.')
            notification = notification[0]

            notifications.remove(notification)
            await session.delete(notification)

            for i, n in enumerate(notifications):
                n.notification_id = i

            await session.commit()

        await ctx.send(f'Removed custom notification: `{id}`')
    
    @commands.command(aliases=['updatenotification'])
    @is_admin()
    async def editnotification(self, ctx: commands.Context, id: int | str, key: str = 'message', *, value: GuildChannel | datetime | timedelta | str | None) -> None:
        '''
        Update an existing notification. (Admin+)
        Key can be "channel", "time", "interval", or "message"
        Format:
        channel: mention, id, or name
        time (UTC): "DD-MM-YYYY HH:MM", "DD/MM/YYYY HH:MM", "DD-MM HH:MM", "DD/MM HH:MM", HH:MM
        interval: HH:MM, [num][unit]* where unit in {d, h, m}, 0 (one time only notification)
        message: string
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used in a server.')

        if not id:
            raise commands.CommandError(message=f'Required argument missing: `id`.')
        if not is_int(id):
            raise commands.CommandError(message=f'Invalid argument: `{id}`. ID must be an integer.')
        else:
            id = int(id)
        
        if not key in ['channel', 'time', 'interval', 'message']:
            raise commands.CommandError(message=f'Invalid argument: `{key}`. Key must be channel, time, interval, or message.')

        if isinstance(value, str):
            value = ' '.join(value).strip()
        if not value:
            raise commands.CommandError(message=f'Required argument missing: `value`.')
        
        async with self.bot.async_session() as session:
            notification: Notification | None = (await session.execute(select(Notification).where(Notification.guild_id == ctx.guild.id).where(Notification.notification_id == id))).scalar_one_or_none()
            if not notification:
                raise commands.CommandError(message=f'Could not find custom notification: `{id}`.')
        
            if key == 'channel':
                channel: str | GuildChannel | datetime | timedelta | None = value
                if channel and not isinstance(channel, GuildChannel):
                    if ctx.message.channel_mentions and isinstance(ctx.message.channel_mentions[0], GuildChannel):
                        channel = ctx.message.channel_mentions[0]
                    elif is_int(channel):
                        channel_by_id: GuildChannel | None = ctx.guild.get_channel(int(channel)) # type: ignore
                        channel = channel_by_id if channel_by_id else str(channel)
                    if isinstance(channel, str):
                        channel = get_text_channel_by_name(ctx.guild, channel)
                if not isinstance(channel, GuildChannel):
                    raise commands.CommandError(f'Could not find channel.')
            
                notification.channel_id = channel.id
            
            elif key == 'time':
                if not isinstance(value, datetime) and not isinstance(value, str):
                    raise commands.CommandError(message=f'Could not parse time: `{value}`')
                time: datetime = parse_datetime_string(value) if isinstance(value, str) else value
                time = time.replace(tzinfo=UTC)
                if time < datetime.now(UTC):
                    raise commands.CommandError(message=f'Invalid argument: `{time}`. Time cannot be in the past.')

                notification.time = time
            
            elif key == 'interval':
                if not isinstance(value, timedelta) and not isinstance(value, str):
                    raise commands.CommandError(message=f'Could not parse interval: `{value}`')
                interval: timedelta | int = parse_timedelta_string(value) if isinstance(value, str) else value

                if (interval.days if interval.days else 0) * 24 * 60 * 60 + (interval.seconds if interval.seconds else 0) > 366 * 24 * 60 * 60:
                    raise commands.CommandError(f'Invalid argument: `{interval}`. Interval cannot exceed 1 year.')
                if 0 < interval.total_seconds() < 900:
                    raise commands.CommandError(f'Invalid argument: `{interval}`. Interval must be at least 15 minutes when set.')
        
                notification.interval = round(interval.total_seconds())
            
            elif isinstance(value, str):
                notification.message = value

            await session.commit()
        
        await ctx.send(f'Notification edited with id: `{id}`\n```channel:  {notification.channel_id}\ntime:     {notification.time} UTC\ninterval: {notification.interval} (seconds)\nmessage:  {notification.message}```')

    @commands.command()
    async def online(self, ctx: commands.Context, *, member: discord.Member, type: int = 1) -> None:
        '''
        Notify next time a user comes online.
        Arguments: member (mention, id, name), (optional: int type [1-4])
        Type 1: (default) notify when status changes to online
        Type 2: notify when status changes to anything but offline
        Type 3: notify when status changes to idle or online (i.e. type 2 excluding dnd)
        Type 4: notify when member goes offline
        Type 1-3 also trigger when the member sends a message
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used in a server.')

        if type in [1,2,3] and str(member.status) == 'online':
            raise commands.CommandError(message=f'Error: `{member.display_name}` is already online.')
        elif type in [2,3] and str(member.status) == 'idle':
            raise commands.CommandError(message=f'Error: `{member.display_name}` is already online.')
        elif type == 2 and str(member.status) == 'dnd':
            raise commands.CommandError(message=f'Error: `{member.display_name}` is already online.')
        elif type == 4 and str(member.status) == 'offline':
            raise commands.CommandError(message=f'Error: `{member.display_name}` is already offline.')
        
        async with self.bot.async_session() as session:
            online_notification: OnlineNotification | None = (await session.execute(select(OnlineNotification).where(OnlineNotification.guild_id == ctx.guild.id)
                                                                                    .where(OnlineNotification.author_id == ctx.author.id).where(OnlineNotification.member_id == member.id))).scalar_one_or_none()
            if online_notification:
                await session.delete(online_notification)
                await session.commit()
                await ctx.send(f'You will no longer be notified of `{member.display_name}`\'s status.')
            else:
                session.add(OnlineNotification(guild_id=ctx.guild.id, author_id=ctx.author.id, member_id=member.id, channel_id=ctx.message.channel.id, type=type))
                await session.commit()
                if type in [1,2,3]:
                    await ctx.send(f'You will be notified when `{member.display_name}` is online.')
                else:
                    await ctx.send(f'You will be notified when `{member.display_name}` is offline.')

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        '''
        Notify users of status updates.
        '''
        if before.status == after.status:
            return
        
        async with self.bot.async_session() as session:
            online_notification: OnlineNotification | None = (await session.execute(select(OnlineNotification).where(OnlineNotification.guild_id == after.guild.id)
                                                                                    .where(OnlineNotification.member_id == after.id))).scalar_one_or_none()
            if not online_notification:
                return
            try:
                channel: discord.TextChannel = get_guild_text_channel(after.guild, online_notification.channel_id)
                user: discord.Member | None = discord.utils.get(after.guild.members, id=online_notification.author_id)
                if not channel or not user:
                    raise commands.CommandError('User or channel not found.')
                if ((online_notification.type in [1,2,3] and str(after.status) == 'online') or (online_notification.type in [2,3] and str(after.status) == 'idle') 
                    or (online_notification.type == 2 and str(after.status) == 'dnd') or (online_notification.type == 4 and str(after.status) == 'offline')):
                    on_or_offline: str = 'offline' if online_notification.type == 4 else 'online'
                    await channel.send(f'`{after.display_name}` is {on_or_offline}! {user.mention}')
                else:
                    return
            except:
                pass

            await session.delete(online_notification)
            await session.commit()
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        '''
        Notify of online status on activity.
        '''
        if message.guild is None:
            return
        
        async with self.bot.async_session() as session:
            online_notification: OnlineNotification | None = (await session.execute(select(OnlineNotification).where(OnlineNotification.guild_id == message.guild.id)
                                                                                    .where(OnlineNotification.member_id == message.author.id))).scalar_one_or_none()
            if not online_notification:
                return
            
            try:
                channel: discord.TextChannel = get_guild_text_channel(message.guild, online_notification.channel_id)
                user: discord.Member | None = discord.utils.get(message.guild.members, id=online_notification.author_id)
                if not channel or not user:
                    raise commands.CommandError('User or channel not found.')
                if online_notification.type in [1,2,3]:
                    await channel.send(f'`{message.author.display_name}` is online! {user.mention}')
                else:
                    return
            except:
                pass

            await session.delete(online_notification)
            await session.commit()

async def setup(bot: Bot) -> None:
    await bot.add_cog(Notifications(bot))
