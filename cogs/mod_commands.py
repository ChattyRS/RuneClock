import re
from typing import Any, List, Sequence
import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context, CommandError
from sqlalchemy import select
from src.message_queue import QueueMessage
from src.bot import Bot
from src.database import Mute, Guild
from datetime import datetime, timedelta, UTC
from src.converters import RoleConverter
from src.database_utils import get_db_guild
from src.discord_utils import get_guild_text_channel
from src.number_utils import is_int
from src.checks import is_admin
from discord.abc import GuildChannel

class ModCommands(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
    
    @commands.command()
    @is_admin()
    async def modmail(self, ctx: Context, public: str | discord.TextChannel = '', private: str | discord.TextChannel = '') -> None:
        '''
        Set up a public and private modmail channel. (Admin+)
        Any messages sent in the public channel will be instantly deleted and then copied to the private channel.
        To disable modmail, use this command without any arguments.
        Arguments:
        public: channel mention
        private: channel mention
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise CommandError(message=f'Required argument missing: `guild`.')

        if not public and not private:
            async with self.bot.async_session() as session:
                guild: Guild = await get_db_guild(self.bot.async_session, ctx.guild, session)
                guild.modmail_public = None
                guild.modmail_private = None
                await session.commit()
            await ctx.send(f'Modmail has been disabled for server **{ctx.guild.name}**.')
            return

        if len(ctx.message.channel_mentions) < 2 or not isinstance(ctx.message.channel_mentions[0], discord.TextChannel) or not isinstance(ctx.message.channel_mentions[1], discord.TextChannel):
            raise CommandError(message=f'Required arguments missing: 2 channel mentions required.')
        
        public, private = ctx.message.channel_mentions[0], ctx.message.channel_mentions[1]

        async with self.bot.async_session() as session:
            guild: Guild = await get_db_guild(self.bot.async_session, ctx.guild, session)
            guild.modmail_public = public.id
            guild.modmail_private = private.id
            await session.commit()

        await ctx.send(f'Modmail public and private channels for server **{ctx.guild.name}** have been set to {public.mention} and {private.mention}.')
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        '''
        Modmail listener

        Args:
            message (discord.Message): The discord message
        '''
        if message.author.bot or message.guild is None or not isinstance(message.channel, discord.TextChannel):
            return
        try:
            guild: Guild = await get_db_guild(self.bot.async_session, message.guild)
        except:
            return
        if guild and guild.modmail_public and guild.modmail_private and message.channel.id == guild.modmail_public:
            embed = discord.Embed(description=f'In: {message.channel.mention}\n“{message.content}”', colour=0x00b2ff, timestamp=message.created_at)
            embed.set_author(name=f'{message.author.display_name} ({message.author.name})', icon_url=message.author.display_avatar.url)
            embed.set_footer(text=f'ID: {message.id}')

            private: discord.TextChannel = get_guild_text_channel(message.guild, guild.modmail_private)

            files: list[discord.File] = []
            if message.attachments:
                for attachment in message.attachments:
                    file: discord.File = await attachment.to_file(filename=attachment.filename, description=attachment.description, use_cached=True)
                    files.append(file)
                embed.set_image(url=f'attachment://{attachment.filename}')
            
            self.bot.queue_message(QueueMessage(private, None, embed, files))

            await message.delete()

    @commands.command()
    @is_admin()
    async def mute(self, ctx: Context, member_name: str | None = None, duration: str | None = None, reason: str | None = None) -> None:
        '''
        Assigns a role 'Muted' to given member. (Admin+)
        Arguments:
        member: name, nickname, id, mention
        duration: [number][unit], where unit in {d, h, m} (optional)
        reason: string (optional)
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not member_name or not ctx.guild:
            raise CommandError(message=f'Required argument missing: `member`.')

        member_mentions: List[discord.Member] = [mention for mention in ctx.message.mentions if isinstance(mention, discord.Member)]
        if member_mentions:
            member: discord.Member | None = member_mentions[0]
        if not member:
            if is_int(member_name):
                member = await ctx.guild.fetch_member(int(member_name))
        if not member:
            member = discord.utils.get(ctx.guild.members, display_name=member_name)
        if not member:
            member = discord.utils.get(ctx.guild.members, name=member_name)

        if not member:
            raise CommandError(message=f'Could not find member: `{member_name}`.')

        mute_role: discord.Role | None = discord.utils.find(lambda r: 'MUTE' in r.name.upper(), ctx.guild.roles)
        if not mute_role:
            try:
                mute_role = await ctx.guild.create_role(name='Muted', permissions=discord.Permissions.none())
            except discord.Forbidden:
                raise CommandError(message=f'Missing permissions: `create_role`.')

        if mute_role in member.roles:
            raise CommandError(message=f'Error: {member.mention} is already muted.')

        try:
            if reason:
                await member.add_roles(mute_role, reason=reason)
            else:
                await member.add_roles(mute_role)
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `role_management`.')

        await ctx.send(f'{member.mention} has been **muted**.')

        if duration:
            # format: [num][unit] where unit in {d, h, m}
            units: List[str] = ['d', 'h', 'm']
            input: list[tuple[int, str]] = []
            num: str | int = ''
            for char in duration.replace(' ', ''):
                if not is_int(char) and not char.lower() in units:
                    raise CommandError(message=f'Invalid argument: `duration`.')
                elif is_int(char):
                    num += char
                elif char.lower() in units:
                    if not num:
                        raise CommandError(message=f'Invalid argument: `duration`.')
                    input.append((int(num), char.lower()))
                    num = ''
            days: int = 0
            hours: int = 0
            minutes: int = 0
            for i in input:
                num = i[0]
                unit: str = i[1]
                if unit == 'd':
                    days += num
                elif unit == 'h':
                    hours += num
                elif unit == 'm':
                    minutes += num
            if days*24*60 + hours*60 + minutes <= 0:
                raise CommandError(message=f'Invalid argument: `duration`.')
            elif days*24*60 + hours*60 + minutes > 60*24*366:
                raise CommandError(message=f'Invalid argument: `duration`.')
            duration_delta: timedelta = timedelta(days=days, hours=hours, minutes=minutes)

            end: datetime = datetime.now(UTC).replace(second=0, microsecond=0) + duration_delta

            async with self.bot.async_session() as session:
                session.add(Mute(guild_id=ctx.guild.id, user_id=member.id, expiration=end, reason=reason))
                await session.commit()

            await ctx.send(f'Mute expiration date set to: `{end}`.')

        for c in ctx.guild.text_channels:
            can_send: bool = c.permissions_for(member).send_messages
            if not can_send:
                continue
            overwritten = False
            for o in c.overwrites:
                obj: discord.Role | discord.Member | Any = o[0] if isinstance(o, list) else o
                if obj == mute_role:
                    overwritten = True
                    break
            if overwritten:
                overwrite: discord.PermissionOverwrite = c.overwrites_for(mute_role)
                if overwrite.send_messages:
                    try:
                        await c.set_permissions(mute_role, send_messages=False)
                    except discord.Forbidden:
                        raise CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')
            else:
                try:
                    await c.set_permissions(mute_role, send_messages=False)
                except discord.Forbidden:
                    raise CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')
            can_send = c.permissions_for(member).send_messages
            if can_send:
                try:
                    await c.set_permissions(member, send_messages=False)
                except discord.Forbidden:
                    raise CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')

    @commands.command()
    @is_admin()
    async def mutes(self, ctx: Context) -> None:
        '''
        Get a list of temp mutes for this server. (Admin+)
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise CommandError(message=f'This command can only be used from a server.')

        msg = 'User ID             Expiration date      Reason\n'
        async with self.bot.async_session() as session:
            mutes: Sequence[Mute] = (await session.execute(select(Mute).where(Mute.guild_id == ctx.guild.id))).scalars().all()
        if not mutes:
            raise CommandError(message=f'No mutes active.')
        
        msg += '\n'.join([f'{mute.user_id}  {mute.expiration}  {mute.reason}' for mute in mutes])

        await ctx.send(f'```{msg}```')

    @commands.command()
    @is_admin()
    async def unmute(self, ctx: Context, *, member: discord.Member) -> None:
        '''
        Unmute a member. (Admin+)
        member: name, nickname, id, mention
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise CommandError(message=f'This command can only be used from a server.')

        mute_role: discord.Role | None = discord.utils.find(lambda r: 'MUTE' in r.name.upper(), ctx.guild.roles)
        if not mute_role:
            raise CommandError(message=f'Missing role: `muted`.')

        if not mute_role in member.roles:
            raise CommandError(message=f'Error: `{member.display_name}` is not muted.')
        else:
            try:
                await member.remove_roles(mute_role)
            except discord.Forbidden:
                raise CommandError(message=f'Missing permissions: `role_management`.')
        
        async with self.bot.async_session() as session:
            mute: Mute | None = (await session.execute(select(Mute).where(Mute.guild_id == ctx.guild.id, Mute.user_id == member.id))).scalar_one_or_none()
            if mute:
                await session.delete(mute)
                await session.commit()

        await ctx.send(f'{member.mention} has been **unmuted**.')

        for c in ctx.guild.text_channels:
            can_send: bool = c.permissions_for(member).send_messages
            if can_send:
                continue
            if member in c.overwrites:
                overwrite: discord.PermissionOverwrite = c.overwrites[member]
                if not overwrite.pair()[1].send_messages:
                    try:
                        await c.set_permissions(member, send_messages=None)
                        c: GuildChannel | None = ctx.guild.get_channel(c.id)
                        if c and member in c.overwrites:
                            overwrite = c.overwrites[member]
                            if not overwrite.pair()[1]:
                                await c.set_permissions(member, overwrite=None)
                    except discord.Forbidden:
                        raise CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')

    @commands.command()
    @is_admin()
    async def kick(self, ctx: Context, *, member: discord.Member) -> None:
        '''
        Kicks the given user (Admin+).
        Arguments: member
        '''
        self.bot.increment_command_counter()

        if isinstance(ctx.author, discord.Member) and member.top_role >= ctx.author.top_role and member.id != self.bot.config['owner']:
            raise CommandError(message=f'You have insufficient permissions to kick this user.')
        try:
            await member.kick()
        except discord.Forbidden:
            raise CommandError(message=f'I have insufficient permissions to kick this user.')

        await ctx.send(f'`{member.display_name}` has been kicked.')

    @commands.command()
    @is_admin()
    async def ban(self, ctx: Context, *, member: discord.Member) -> None:
        '''
        Bans the given user (Admin+).
        Arguments: member
        '''
        self.bot.increment_command_counter()

        if isinstance(ctx.author, discord.Member) and member.top_role >= ctx.author.top_role and member.id != self.bot.config['owner']:
            raise CommandError(message=f'You have insufficient permissions to ban this user.')
        try:
            await member.ban()
        except discord.Forbidden:
            raise CommandError(message=f'I have insufficient permissions to ban this user.')

        await ctx.send(f'`{member.display_name}` has been banned.')

    @commands.command(pass_context=True, aliases=['delete', 'clear'])
    @is_admin()
    async def purge(self, ctx: Context, num: int | str = 0) -> None:
        '''
        Deletes given amount of messages (Admin+).
        Arguments: integer.
        Constraints: You can delete up to 100 messages at a time.
        '''
        self.bot.increment_command_counter()

        if not isinstance(ctx.channel, discord.TextChannel):
            raise CommandError(message=f'Invalid channel type.')

        if not isinstance(num, int):
            if is_int(num):
                num = int(num)
            else:
                raise CommandError(message=f'Invalid argument: `{num}`.')

        if not num or num < 1 or num > 100:
            raise CommandError(message=f'Invalid argument: `{num}`.')
        try:
            try:
                await ctx.message.delete()
            except:
                pass
            await ctx.channel.purge(limit=num)
            await ctx.send(f'{num} messages deleted!', delete_after = 3)
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `delete_message`.')

    @commands.command(pass_context=True)
    @is_admin()
    async def role(self, ctx: Context, role: RoleConverter, *, member: discord.Member) -> None:
        '''
        Toggles the given role for the given user (Admin+).
        Arguments: role, member
        '''
        self.bot.increment_command_counter()

        if not role or not isinstance(role, discord.Role):
            raise CommandError(message=f'Could not convert role.')

        if isinstance(ctx.author, discord.Member) and member.top_role >= ctx.author.top_role and member.id != self.bot.config['owner']:
            raise CommandError(message=f'You have insufficient permissions to edit this user\'s roles.')
        if isinstance(ctx.author, discord.Member) and role > ctx.author.top_role and member.id != self.bot.config['owner']:
            raise CommandError(message=f'You have insufficient permissions to assign or remove this role.')

        if not role in member.roles:
            try:
                await member.add_roles(role)
                await ctx.send(f'**{member.display_name}** has been given role `{role.name}`.')
            except discord.Forbidden:
                raise CommandError(message=f'I have insufficient permissions to assign this role to this user.')
        else:
            try:
                await member.remove_roles(role)
                await ctx.send(f'**{member.display_name}** has been removed from role `{role.name}`.')
            except discord.Forbidden:
                raise CommandError(message=f'I have insufficient permissions to remove this role from this user.')

    @commands.command(pass_context=True, aliases=['mention'])
    @is_admin()
    async def mentionable(self, ctx: Context, role: RoleConverter) -> None:
        '''
        Toggles mentionable for the given role (Admin+).
        Arguments: role
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not role or not isinstance(role, discord.Role):
            raise CommandError(message=f'Could not convert role.')
        
        emoji: str = ':no_entry_sign:' if role.mentionable else ':white_check_mark:'
        not_if_off: str = 'not ' if role.mentionable else ''
        message: str = f'{emoji} Role **{role.name}** has been made **{not_if_off}mentionable**.'
        
        try:
            await role.edit(mentionable = not role.mentionable)
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `edit_role`.')
        await ctx.send(message)

    @commands.command(pass_context=True, aliases=['rolecolor'])
    @is_admin()
    async def rolecolour(self, ctx: Context, role: RoleConverter, colour: str | discord.Colour = "") -> None:
        '''
        Changes the colour of the given role to the given colour (Admin+).
        Arguments: role, #hexcode
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise CommandError(message=f'This command can only be used from a server.')

        if not role or not isinstance(role, discord.Role):
            raise CommandError(message=f'Could not convert role.')

        if not colour:
            raise CommandError(message=f'Required argument(s) missing: `colour`.')

        if not isinstance(colour, discord.Colour) and not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', colour):
            raise CommandError(message=f'Invalid argument: `{colour}`.')
        
        colour = discord.Colour(int(colour.replace("#", "0x"), 16)) if isinstance(colour, str) else colour

        try:
            await role.edit(colour=colour)
            await ctx.send(f'The colour for role **{role.name}** has been changed to **{str(colour)}**.')
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `edit_role`.')

    @commands.command(pass_context=True, aliases=['changenick', 'nick'])
    async def setnick(self, ctx: Context, *, username: str | None) -> None:
        '''
        Changes the user's nickname.
        Arguments: nickname
        If no nickname is given, your nickname will be removed.
        Constraints: nickname must be a valid RSN
        '''
        self.bot.increment_command_counter()

        if not isinstance(ctx.author, discord.Member):
            raise CommandError(message=f'User is not a guild member.')
        
        username = username.replace('_', '').strip() if username else None
        if not username:
            try:
                await ctx.author.edit(nick=None)
                await ctx.send(f'Your nickname has been removed.')
                return
            except discord.Forbidden:
                raise CommandError(message=f'Missing permissions: `manage_nicknames`.')
        if len(username) > 12:
            raise CommandError(message=f'Invalid argument: `{username}`. Character limit exceeded.')
        if re.match(r'^[A-z0-9 -]+$', username) is None:
            raise CommandError(message=f'Invalid argument: `{username}`. Forbidden character.')
        try:
            await ctx.author.edit(nick=username)
            await ctx.send(f'Your nickname has been changed to **{username}**.')
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `manage_nicknames`.')
    
    @commands.command()
    @is_admin()
    async def edit_nick(self, ctx: Context, member: discord.Member, *, nickname: str | None) -> None:
        '''
        Edits the nickname of the given user.
        '''
        if not nickname:
            raise CommandError(message=f'Required argument missing: `nickname`.')
        try:
            nickname = nickname.replace(member.mention, '')
            await member.edit(nick=nickname)
            await ctx.send(f'`{member.name}`\'s nickname has been changed to `{nickname}`.')
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `manage_nicknames`. Or insufficient permissions to change {member.display_name}\'s nickname.')

async def setup(bot: Bot) -> None:
    await bot.add_cog(ModCommands(bot))
