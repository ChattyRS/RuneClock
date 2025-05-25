import asyncio
from typing import Sequence
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from sqlalchemy import select
from src.message_queue import QueueMessage
from src.bot import Bot
from src.database import Guild, Role
from datetime import datetime, UTC
from src.database_utils import get_db_guild
from src.date_utils import months
from discord.abc import GuildChannel
from src.discord_utils import find_guild_text_channel

class Logs(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    def log_event(self) -> None:
        self.bot.events_logged += 1

    @Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if len(str(error).split('\"')) == 3:
            if str(error).split('\"')[0] == "Command " and str(error).split('\"')[2] == " is not found":
                return
        try:
            username: str = self.bot.config['pc_username']
            error_str: str = str(error).replace(username, 'user')
            error_str = discord.utils.escape_mentions(text=error_str)
            msg: discord.Message = await ctx.send(error_str)
            await asyncio.sleep(10)
            await ctx.message.delete()
            await msg.delete()
        except:
            pass

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        async with self.bot.db.get_session() as session:
            guild: Guild = await get_db_guild(session, member.guild)

        channel = None
        if guild and guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(member.guild, guild.log_channel_id)
        if not channel:
            return
        self.log_event()
        title: str = f'**Member Joined**'
        colour = 0x00e400
        timestamp: datetime = datetime.now(UTC)
        id: str = f'User ID: {member.id}'
        creation_time: datetime = member.created_at
        min: int | str = creation_time.minute
        if len(str(min)) == 1:
            min = '0' + str(min)
        hour: int = creation_time.hour
        time: str = f'{creation_time.day} {months[creation_time.month-1]} {creation_time.year}, {hour}:{min}'
        txt: str = (f'{member.mention} ({member.name})\n'
            f'Account creation: {time}')
        url: str = member.display_avatar.url
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        embed.set_thumbnail(url=url)
        self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        async with self.bot.db.get_session() as session:
            guild: Guild = await get_db_guild(session, member.guild)

        channel = None
        if guild and guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(member.guild, guild.log_channel_id)
        if not channel:
            return
        try:
            banlist: list[discord.User] = [ban_entry.user async for ban_entry in member.guild.bans()]
            if member._user in banlist:
                return
        except discord.Forbidden:
            pass
        self.log_event()
        title: str = f'**Member Left**'
        colour = 0xff0000
        timestamp: datetime = datetime.now(UTC)
        id: str = f'User ID: {member.id}'
        txt: str = f'{member.mention} ({member.name})'
        url: str = member.display_avatar.url
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        embed.set_thumbnail(url=url)
        self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, guild)

        channel = None
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(guild, db_guild.log_channel_id)
        if not channel:
            return
        
        self.log_event()
        title: str = f'**Member Banned**'
        colour = 0xff0000
        timestamp: datetime = datetime.now(UTC)
        id: str = f'User ID: {user.id}'
        txt: str = f'{user.mention} ({user.name})'
        url: str = user.display_avatar.url
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        embed.set_thumbnail(url=url)
        self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, guild)

        channel = None
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(guild, db_guild.log_channel_id)
        if not channel:
            return
        
        self.log_event()
        title: str = f'**Member Unbanned**'
        colour = 0xff7b1f
        timestamp: datetime = datetime.now(UTC)
        id: str = f'User ID: {user.id}'
        txt: str = f'{user.name}'
        url: str = user.display_avatar.url
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        embed.set_thumbnail(url=url)
        self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, message.guild)

        channel = None
        if not message.guild or not isinstance(message.channel, discord.TextChannel):
            return
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(message.guild, db_guild.log_channel_id)
        if not channel:
            return
        
        if db_guild.log_bots == False and message.author.bot:
            return
        self.log_event()
        
        txt = (f'By: {message.author.mention} ({message.author.name})\n'
               f'In: {message.channel.mention}')
        embed = discord.Embed(title='**Message Deleted**', colour=0x00b2ff, timestamp=datetime.now(UTC), description=txt)
        msg = message.content
        if len(msg) > 1000:
            msg = msg[:1000] + '\n...'
        if not msg:
            msg = 'N/A'
        embed.add_field(name='Message', value=msg, inline=False)
        embed.set_footer(text=f'Message ID: {message.id}')
        embed.set_thumbnail(url=message.author.display_avatar.url)
        self.bot.queue_message(QueueMessage(channel, None, embed))
    
    @Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, messages[0].guild)

        channel = None
        if not messages[0].guild or not isinstance(messages[0].channel, discord.TextChannel):
            return
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(messages[0].guild, db_guild.log_channel_id)
        if not channel:
            return
        
        self.log_event()

        txt: str = f'{len(messages)} messages deleted in {messages[0].channel.mention}'
        embed = discord.Embed(title='**Bulk delete**', colour=0x00b2ff, timestamp=datetime.now(UTC), description=txt)
        self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, before.guild)

        channel = None
        if not before.guild or not isinstance(after.channel, discord.TextChannel):
            return
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(before.guild, db_guild.log_channel_id)
        if not channel:
            return
        
        if db_guild.log_bots == False and after.author.bot:
            return

        member: discord.Member | discord.User = after.author
        if member.bot or before.embeds or after.embeds: # don't log edits for bots or embeds
            return
        if after.content != before.content:
            self.log_event()
            title: str = f'**Message Edited**'
            colour = 0x00b2ff
            timestamp: datetime = datetime.now(UTC)
            id: str = f'Message ID: {after.id}'
            txt: str = (f'By: {member.mention} ({member.name})\n'
                   f'In: {after.channel.mention}')
            url: str = member.display_avatar.url
            beforeContent: str = before.content
            if not beforeContent:
                beforeContent = 'N/A'
            afterContent: str = after.content
            if not afterContent:
                afterContent = 'N/A'
            if len(beforeContent) > 1000:
                beforeContent = beforeContent[:1000] + '\n...'
            if len(afterContent) > 1000:
                afterContent = afterContent[:1000] + '\n...'
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            embed.add_field(name='Before', value=beforeContent, inline=False)
            embed.add_field(name='After', value=afterContent, inline=False)
            embed.set_footer(text=id)
            embed.set_thumbnail(url=url)
            self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: GuildChannel) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, channel.guild)

        log_channel = None
        if db_guild and db_guild.log_channel_id:
            log_channel: discord.TextChannel | None = find_guild_text_channel(channel.guild, db_guild.log_channel_id)
        if not log_channel:
            return
        
        self.log_event()
        title: str = f'**Channel Deleted**'
        colour = 0xff0000
        timestamp: datetime = datetime.now(UTC)
        id: str = f'Channel ID: {channel.id}'
        creation_time: datetime = channel.created_at
        time: str = f'{creation_time.day} {months[creation_time.month-1]} {creation_time.year}, {creation_time.hour}:{creation_time.minute}'
        txt: str = (f'**{channel.name}** was deleted\n'
               f'Channel creation: {time}.')
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        self.bot.queue_message(QueueMessage(log_channel, None, embed))

    @Cog.listener()
    async def on_guild_channel_create(self, channel: GuildChannel) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, channel.guild)

        log_channel = None
        if db_guild and db_guild.log_channel_id:
            log_channel: discord.TextChannel | None = find_guild_text_channel(channel.guild, db_guild.log_channel_id)
        if not log_channel:
            return
        
        self.log_event()
        title: str = f'**Channel Created**'
        colour = 0x00e400
        timestamp: datetime = datetime.now(UTC)
        id: str = f'Channel ID: {channel.id}'
        txt: str = f'{channel.mention}'
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        self.bot.queue_message(QueueMessage(log_channel, None, embed))

    @Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, before.guild)

        channel = None
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(before.guild, db_guild.log_channel_id)
        if not channel:
            return

        if before.nick != after.nick:
            self.log_event()
            title: str = f'**Nickname Changed**'
            colour = 0x00b2ff
            timestamp: datetime = datetime.now(UTC)
            id: str = f'User ID: {after.id}'
            txt: str = f'{after.mention} ({after.name})'
            url: str = after.display_avatar.url
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            before_nick: str | None = before.nick
            if not before_nick:
                before_nick = 'N/A'
            after_nick: str | None = after.nick
            if not after_nick:
                after_nick = 'N/A'
            embed.add_field(name='Before', value=before_nick, inline=False)
            embed.add_field(name='After', value=after_nick, inline=False)
            embed.set_footer(text=id)
            embed.set_thumbnail(url=url)
            self.bot.queue_message(QueueMessage(channel, None, embed))
        elif set(before.roles) != set(after.roles):
            self.log_event()
            added_roles: list[discord.Role] = []
            removed_roles: list[discord.Role] = []
            for r in before.roles:
                if not r in after.roles:
                    removed_roles.append(r)
            for r in after.roles:
                if not r in before.roles:
                    added_roles.append(r)
            title = f'**Roles Changed**'
            colour = 0x00b2ff
            timestamp = datetime.now(UTC)
            id = f'User ID: {after.id}'
            txt = f'{after.mention} ({after.name})'
            url = after.display_avatar.url
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            added: str = ""
            if added_roles:
                count = 0
                for role in added_roles:
                    count += 1
                    added += role.name
                    if count < len(added_roles):
                        added += ", "
                embed.add_field(name='Added', value=added, inline=False)
            removed: str = ""
            if removed_roles:
                count = 0
                for role in removed_roles:
                    count += 1
                    removed += role.name
                    if count < len(removed_roles):
                        removed += ", "
                embed.add_field(name='Removed', value=removed, inline=False)
            embed.set_footer(text=id)
            embed.set_thumbnail(url=url)
            self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, before)

        channel = None
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(before, db_guild.log_channel_id)
        if not channel:
            return
        
        if before.name != after.name:
            self.log_event()
            owner: discord.Member | None = after.owner
            title: str = f'**Server Name Changed**'
            colour = 0x00b2ff
            timestamp: datetime = datetime.now(UTC)
            id: str = f'Server ID: {after.id}'
            txt: str | None = f'Owner: {owner.mention} ({owner.name})' if owner else None
            url: str | None = after.icon.url if after.icon else None
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            before_name: str = before.name
            if not before_name:
                before_name = 'N/A'
            after_name: str = after.name
            if not after_name:
                after_name = 'N/A'
            embed.add_field(name='Before', value=before_name, inline=False)
            embed.add_field(name='After', value=after_name, inline=False)
            embed.set_footer(text=id)
            embed.set_thumbnail(url=url)
            self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, role.guild)

        channel = None
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(role.guild, db_guild.log_channel_id)
        if not channel:
            return
        
        self.log_event()
        title: str = f'**Role Created**'
        colour = 0x00e400
        timestamp: datetime = datetime.now(UTC)
        id: str = f'Role ID: {role.id}'
        txt: str = f'{role.mention}'
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        async with self.bot.db.get_session() as session:
            db_role: Role | None = (await session.execute(select(Role).where(Role.guild_id == role.guild.id, Role.role_id == role.id))).scalar_one_or_none()
            if db_role:
                await session.delete(db_role)
            db_guild: Guild = await get_db_guild(session, role.guild)
            await session.commit()

        channel = None
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(role.guild, db_guild.log_channel_id)
        if not channel:
            return

        self.log_event()
        title: str = f'**Role Deleted**'
        colour = 0xff0000
        timestamp: datetime = datetime.now(UTC)
        id: str = f'Role ID: {role.id}'
        txt: str = f'{role.name}'
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, before.guild)

        channel = None
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(before.guild, db_guild.log_channel_id)
        if not channel:
            return
        
        if before.name != after.name:
            self.log_event()
            title: str = f'**Role Name Changed**'
            colour = 0x00b2ff
            timestamp: datetime = datetime.now(UTC)
            id: str = f'Role ID: {after.id}'
            txt: str = f'Role: {after.mention}'
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            embed.add_field(name='Before', value=before.name, inline=False)
            embed.add_field(name='After', value=after.name, inline=False)
            embed.set_footer(text=id)
            self.bot.queue_message(QueueMessage(channel, None, embed))

    @Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]) -> None:
        async with self.bot.db.get_session() as session:
            db_guild: Guild = await get_db_guild(session, guild)

        channel = None
        if db_guild and db_guild.log_channel_id:
            channel: discord.TextChannel | None = find_guild_text_channel(guild, db_guild.log_channel_id)
        if not channel:
            return

        if len(before) != len(after):
            self.log_event()
            added = False
            new_emoji: discord.Emoji | None = None
            name: str | None = None
            animated = False
            if len(before) > len(after):
                title: str = f'Emoji Deleted'
                for e in before:
                    if not e in after:
                        name = e.name
                        animated: bool = e.animated
                        break
                if animated:
                    title = f'Animated Emoji Deleted'
                colour = 0xff0000
            else:
                title = f'Emoji Added'
                for e in after:
                    if not e in before:
                        name = e.name
                        added = True
                        new_emoji = e
                        animated = e.animated
                        break
                if animated:
                    title = 'Animated Emoji Added'
                colour = 0x00e400
            timestamp: datetime = datetime.now(UTC)
            id: str = f'Server ID: {guild.id}'
            txt: str = ''
            if added and new_emoji:
                try:
                    new_emoji_fetched: discord.Emoji = await guild.fetch_emoji(new_emoji.id)
                    txt = f'Added by {new_emoji_fetched.user.mention}:\n' if new_emoji_fetched.user else ''
                except:
                    pass
                txt += f'{new_emoji} `{name}`\n'
            else:
                txt = f'`{name}`'
            length = 0
            if animated:
                for e in after:
                    if e.animated:
                        length += 1
                txt += f'\n{length}/{guild.emoji_limit} animated emojis'
            else:
                for e in after:
                    if not e.animated:
                        length += 1
                txt += f'\n{length}/{guild.emoji_limit} emojis'

            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            embed.set_footer(text=id)
            self.bot.queue_message(QueueMessage(channel, None, embed))
            return
        before_names: list[str] = []
        for e in before:
            before_names.append(e.name)
        after_names: list[str] = []
        for e in after:
            after_names.append(e.name)
        old_name: str = ''
        new_name: str = ''
        after_emoji: discord.Emoji | None = None
        for name in before_names:
            if not name in after_names:
                old_name = name
        for name in after_names:
            if not name in before_names:
                new_name = name
                for e in after:
                    if e.name == name:
                        after_emoji = e
                        break
        if old_name and new_name and after_emoji:
            self.log_event()
            title = f'Emoji name changed'
            colour = 0x00b2ff
            timestamp = datetime.now(UTC)
            txt = f'Before: {old_name}\nAfter: {new_name}\n{str(after_emoji)}'
            id = f'Server ID: {guild.id}'
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            embed.set_footer(text=id)
            self.bot.queue_message(QueueMessage(channel, None, embed))

async def setup(bot: Bot) -> None:
    await bot.add_cog(Logs(bot))
