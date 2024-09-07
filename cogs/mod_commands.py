import asyncio
from typing import List
import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context, CommandError
from bot import Bot, Mute, Guild
from datetime import datetime, timedelta, UTC
from converters import RoleConverter
from database_utils import get_db_guild
from discord_utils import get_guild_text_channel
from number_utils import is_int
from checks import is_admin

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
                guild: Guild = await get_db_guild(self.bot, ctx.guild, session)
                guild.modmail_public = None
                guild.modmail_private = None
                await session.commit()
            await ctx.send(f'Modmail has been disabled for server **{ctx.guild.name}**.')
            return

        if len(ctx.message.channel_mentions) < 2 or not isinstance(ctx.message.channel_mentions[0], discord.TextChannel) or not isinstance(ctx.message.channel_mentions[1], discord.TextChannel):
            raise CommandError(message=f'Required arguments missing: 2 channel mentions required.')
        
        public, private = ctx.message.channel_mentions[0], ctx.message.channel_mentions[1]

        async with self.bot.async_session() as session:
            guild: Guild = await get_db_guild(self.bot, ctx.guild, session)
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
            guild: Guild = await get_db_guild(self.bot, message.guild)
        except:
            return
        if guild and guild.modmail_public and guild.modmail_private and message.channel.id == guild.modmail_public:
            embed = discord.Embed(description=f'In: {message.channel.mention}\n“{message.content}”', colour=0x00b2ff, timestamp=message.created_at)
            embed.set_author(name=f'{message.author.display_name} ({message.author.name})', icon_url=message.author.display_avatar.url)
            embed.set_footer(text=f'ID: {message.id}')

            await message.delete()

            private: discord.TextChannel = get_guild_text_channel(message.guild, guild.modmail_private)

            if message.attachments:
                attachment: discord.Attachment = message.attachments[0]
                file: discord.File = await attachment.to_file(filename=attachment.filename, description=attachment.description)
                embed.set_image(url=f'attachment://{attachment.filename}')
                await private.send(embed=embed, file=file)
            else:
                await private.send(embed=embed)

    @commands.command()
    @is_admin()
    async def mute(self, ctx: Context, member='', duration='', reason='N/A') -> None:
        '''
        Assigns a role 'Muted' to given member. (Admin+)
        Arguments:
        member: name, nickname, id, mention
        duration: [number][unit], where unit in {d, h, m} (optional)
        reason: string (optional)
        '''
        increment_command_counter()
        await ctx.channel.typing()
        
        msg = ctx.message
        guild = ctx.guild

        if not member or not guild:
            raise CommandError(message=f'Required argument missing: `member`.')

        temp = None
        member_mentions = [mention for mention in msg.mentions if isinstance(mention, discord.Member)]
        if member_mentions:
            temp = member_mentions[0]
        if not temp:
            if is_int(member):
                temp = await guild.fetch_member(int(member))
        if not temp:
            temp = discord.utils.get(guild.members, display_name=member)
        if not temp:
            temp = discord.utils.get(guild.members, name=member)

        if not temp:
            raise CommandError(message=f'Could not find member: `{member}`.')
        member = temp

        mute_role = discord.utils.find(lambda r: 'MUTE' in r.name.upper(), guild.roles)
        if not mute_role:
            try:
                mute_role = await guild.create_role(name='Muted', permissions=discord.Permissions.none())
            except discord.Forbidden:
                raise CommandError(message=f'Missing permissions: `create_role`.')

        if mute_role in member.roles:
            raise CommandError(message=f'Error: {member.mention} is already muted.')

        try:
            if not reason == 'N/A':
                await member.add_roles(mute_role, reason=reason)
            else:
                await member.add_roles(mute_role)
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `role_management`.')

        await ctx.send(f'{member.mention} has been **muted**.')

        if duration:
            # format: [num][unit] where unit in {d, h, m}
            temp = duration.replace(' ', '')
            units = ['d', 'h', 'm']
            input = []
            num = ''
            for char in temp:
                if not is_int(char) and not char.lower() in units:
                    raise CommandError(message=f'Invalid argument: `duration`.')
                elif is_int(char):
                    num += char
                elif char.lower() in units:
                    if not num:
                        raise CommandError(message=f'Invalid argument: `duration`.')
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
                raise CommandError(message=f'Invalid argument: `duration`.')
            elif days*24*60 + hours*60 + minutes > 60*24*366:
                raise CommandError(message=f'Invalid argument: `duration`.')
            duration = timedelta(days=days, hours=hours, minutes=minutes)

            end = str(datetime.now(UTC).replace(second=0, microsecond=0) + duration)

            await Mute.create(guild_id=ctx.guild.id, user_id=member.id, expiration=end, reason=reason)

            await ctx.send(f'Mute expiration date set to: `{end}`.')

        for c in guild.text_channels:
            send = c.permissions_for(member).send_messages
            if not send:
                continue
            overwritten = False
            for o in c.overwrites:
                obj = o[0] if isinstance(o, List) else o
                if obj == mute_role:
                    overwritten = True
                    break
            if overwritten:
                o = c.overwrites_for(mute_role)
                if o.send_messages:
                    try:
                        await c.set_permissions(mute_role, send_messages=False)
                    except discord.Forbidden:
                        raise CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')
            else:
                try:
                    await c.set_permissions(mute_role, send_messages=False)
                except discord.Forbidden:
                    raise CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')
            send = c.permissions_for(member).send_messages
            if send:
                try:
                    await c.set_permissions(member, send_messages=False)
                except discord.Forbidden:
                    raise CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')

    @commands.command()
    @is_admin()
    async def mutes(self, ctx: Context):
        '''
        Get a list of temp mutes for this server. (Admin+)
        '''
        increment_command_counter()

        msg = 'User ID             Expiration date      Reason'
        mutes = await Mute.query.where(Mute.guild_id==ctx.guild.id).gino.all()
        if not mutes:
            raise CommandError(message=f'No mutes active.')
    
        for mute in mutes:
            msg += f'\n{mute.user_id}  {mute.expiration}  {mute.reason}'

        await ctx.send(f'```{msg}```')

    @commands.command()
    @is_admin()
    async def unmute(self, ctx: Context, member):
        '''
        Unmute a member. (Admin+)
        member: name, nickname, id, mention
        '''
        increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise CommandError(message=f'Required argument missing: `guild`.')
        
        msg = ctx.message
        guild = ctx.guild

        temp = None
        member_mentions = [mention for mention in msg.mentions if isinstance(mention, discord.Member)]
        if member_mentions:
            temp = member_mentions[0]
        if not temp:
            if is_int(member):
                temp = await guild.fetch_member(int(member))
        if not temp:
            temp = discord.utils.get(guild.members, display_name=member)
        if not temp:
            temp = discord.utils.get(guild.members, name=member)

        if not temp:
            raise CommandError(message=f'Could not find member: `{member}`.')
        member = temp

        mute_role = discord.utils.find(lambda r: 'MUTE' in r.name.upper(), guild.roles)
        if not mute_role:
            raise CommandError(message=f'Missing role: `muted`.')

        if not mute_role in member.roles:
            raise CommandError(message=f'Error: `{member.display_name}` is not muted.')
        else:
            try:
                await member.remove_roles(mute_role)
            except discord.Forbidden:
                raise CommandError(message=f'Missing permissions: `role_management`.')
        
        mute = await Mute.query.where(Mute.guild_id==ctx.guild.id).where(Mute.user_id==member.id).gino.first()
        if mute:
            await mute.delete()

        await ctx.send(f'{member.mention} has been **unmuted**.')

        for c in guild.text_channels:
            send = c.permissions_for(member).send_messages
            if send:
                continue
            if member in c.overwrites:
                overwrite = c.overwrites[member]
                if not overwrite.pair()[1].send_messages:
                    try:
                        await c.set_permissions(member, send_messages=None)
                        c = guild.get_channel(c.id)
                        if c and member in c.overwrites:
                            overwrite = c.overwrites[member]
                            if not overwrite.pair()[1]:
                                await c.set_permissions(member, overwrite=None)
                    except discord.Forbidden:
                        raise CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')

    @commands.command()
    @is_admin()
    async def kick(self, ctx: Context, *, member: discord.Member):
        '''
        Kicks the given user (Admin+).
        Arguments: member
        '''
        increment_command_counter()

        if isinstance(ctx.author, discord.Member) and member.top_role >= ctx.author.top_role and member.id != config['owner']:
            raise CommandError(message=f'You have insufficient permissions to kick this user.')
        try:
            await member.kick()
        except discord.Forbidden:
            raise CommandError(message=f'I have insufficient permissions to kick this user.')

        await ctx.send(f'`{member.display_name}` has been kicked.')

    @commands.command()
    @is_admin()
    async def ban(self, ctx: Context, *, member: discord.Member):
        '''
        Bans the given user (Admin+).
        Arguments: member
        '''
        increment_command_counter()

        if isinstance(ctx.author, discord.Member) and member.top_role >= ctx.author.top_role and member.id != config['owner']:
            raise CommandError(message=f'You have insufficient permissions to ban this user.')
        try:
            await member.ban()
        except discord.Forbidden:
            raise CommandError(message=f'I have insufficient permissions to ban this user.')

        await ctx.send(f'`{member.display_name}` has been banned.')

    @commands.command(pass_context=True, aliases=['delete', 'clear'])
    @is_admin()
    async def purge(self, ctx: Context, num=0):
        '''
        Deletes given amount of messages (Admin+).
        Arguments: integer.
        Constraints: You can delete up to 100 messages at a time.
        '''
        increment_command_counter()

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
            msg = await ctx.send(f'{num} messages deleted!')
            await asyncio.sleep(3)
            await msg.delete()
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `delete_message`.')

    @commands.command(pass_context=True)
    @is_admin()
    async def role(self, ctx: Context, role: RoleConverter, *, member: discord.Member):
        '''
        Toggles the given role for the given user (Admin+).
        Arguments: role, member
        '''
        increment_command_counter()

        if not role or not isinstance(role, discord.Role):
            raise CommandError(message=f'Could not convert role.')

        if isinstance(ctx.author, discord.Member) and member.top_role >= ctx.author.top_role and member.id != config['owner']:
            raise CommandError(message=f'You have insufficient permissions to edit this user\'s roles.')
        if isinstance(ctx.author, discord.Member) and role > ctx.author.top_role and member.id != config['owner']:
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
    async def mentionable(self, ctx: Context, role_name=""):
        '''
        Toggles mentionable for the given role (Admin+).
        Arguments: role
        '''
        increment_command_counter()
        await ctx.channel.typing()

        guild = ctx.guild

        if not role_name or not guild:
            raise CommandError(message=f'Required argument missing: `role`.')
        role = ""
        for r in guild.roles:
            if role_name.upper() == r.name.upper():
                role = r
                break
        if not role:
            for r in guild.roles:
                if role_name.upper() in r.name.upper():
                    role = r
                    break
        if not role:
            raise CommandError(message=f'Could not find role: `{role_name}`.')
        else:
            mentionable = role.mentionable
            emoji = ""
            x = ""
            if mentionable:
                mentionable = False
                emoji = ":no_entry_sign: "
                x = "not "
            else:
                emoji = ":white_check_mark: "
                mentionable = True
            try:
                await role.edit(mentionable=mentionable)
            except discord.Forbidden:
                raise CommandError(message=f'Missing permissions: `edit_role`.')
            await ctx.send(f'{emoji}Role **{role.name}** has been made **{x}mentionable**.')

    @commands.command(pass_context=True, aliases=['rolecolor'])
    @is_admin()
    async def rolecolour(self, ctx: Context, role_name="", colour=""):
        '''
        Changes the colour of the given role to the given colour (Admin+).
        Arguments: role, #hexcode
        '''
        increment_command_counter()
        await ctx.channel.typing()

        if not role_name or not colour or not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise CommandError(message=f'Required argument(s) missing: `role/colour`.')

        guild = ctx.guild
        roles = guild.roles
        role_exists = False
        role: discord.Role
        for r in roles:
            if r.name.upper() == role_name.upper():
                role = r
                role_exists = True
                break
        if not role_exists:
            raise CommandError(message=f'Could not find role: `{role_name}`.')
        match = re.search(r'^#(?:[0-9a-fA-F]{3}){1,2}$', colour)
        if not match:
            raise CommandError(message=f'Invalid argument: `{colour}`.')
        colour = discord.Colour(int(colour.replace("#", "0x"), 16))
        roles = ctx.author.roles
        try:
            await role.edit(colour=colour)
            await ctx.send(f'The colour for role **{role.name}** has been changed to **{str(colour)}**.')
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `edit_role`.')

    @commands.command(pass_context=True, aliases=['changenick', 'nick'])
    async def setnick(self, ctx: Context, *username):
        '''
        Changes the user's nickname.
        Arguments: nickname
        If no nickname is given, your nickname will be removed.
        Constraints: nickname must be a valid RSN
        '''
        increment_command_counter()

        if not isinstance(ctx.author, discord.Member):
            raise CommandError(message=f'User is not a guild member.')
        
        input = ''
        for word in username:
            input += word + ' '
        input = input.replace('_', ' ')
        input = input.strip()
        if not input:
            try:
                await ctx.author.edit(nick=None)
                await ctx.send(f'Your nickname has been removed.')
                return
            except discord.Forbidden:
                raise CommandError(message=f'Missing permissions: `manage_nicknames`.')
        if len(input) > 12:
            raise CommandError(message=f'Invalid argument: `{input}`. Character limit exceeded.')
        if re.match('^[A-z0-9 -]+$', input) is None:
            raise CommandError(message=f'Invalid argument: `{input}`. Forbidden character.')
        try:
            await ctx.author.edit(nick=input)
            await ctx.send(f'Your nickname has been changed to **{input}**.')
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `manage_nicknames`.')
    
    @commands.command()
    @is_admin()
    async def edit_nick(self, ctx: Context, member: discord.Member, *nickname):
        '''
        Edits the nickname of the given user.
        '''
        nickname = ' '.join(nickname)
        if not nickname:
            raise CommandError(message=f'Required argument missing: `nickname`.')
        try:
            await member.edit(nick=nickname)
            await ctx.send(f'`{member.name}`\'s nickname has been changed to `{nickname}`.')
        except discord.Forbidden:
            raise CommandError(message=f'Missing permissions: `manage_nicknames`. Or insufficient permissions to change {member.display_name}\'s nickname.')

    @commands.command(aliases=['delall'])
    @is_admin()
    async def deleteall(self, ctx: Context, channel=''):
        '''
        Deletes all messages that will be sent in the given channel. (Admin+)
        Arguments: channel (mention, name, or id)
        '''
        increment_command_counter()

        if not channel or not ctx.guild:
            raise CommandError(message=f'Required argument missing: `channel`.')
        elif ctx.message.channel_mentions:
            channel = ctx.message.channel_mentions[0]
        else:
            found = False
            if is_int(channel):
                for c in ctx.guild.text_channels:
                    if c.id == int(channel):
                        channel = c
                        found = True
                        break
            if not found and isinstance(channel, str):
                for c in ctx.guild.text_channels:
                    if c.name.upper() == channel.upper():
                        channel = c
                        found = True
                        break
            if not found and isinstance(channel, str):
                for c in ctx.guild.text_channels:
                    if channel.upper() in c.name.upper():
                        channel = c
                        found = True
                        break
            if not found:
                raise CommandError(message=f'Could not find channel: `{channel}`.')
            
        if not isinstance(channel, discord.TextChannel):
            raise CommandError(message=f'Could not find channel: `{channel}`.')

        guild = await Guild.get(ctx.guild.id)
        if guild.delete_channel_ids:
            if channel.id in guild.delete_channel_ids:
                await guild.update(delete_channel_ids=guild.delete_channel_ids.remove(channel.id)).apply()
                await ctx.send(f'Messages in {channel.mention} will no longer be deleted.')
            else:
                await guild.update(delete_channel_ids=guild.delete_channel_ids + [channel.id]).apply()
                await ctx.send(f'All future messages in {channel.mention} will be deleted.')
        else:
            await guild.update(delete_channel_ids=[channel.id]).apply()
            await ctx.send(f'All future messages in {channel.mention} will be deleted.')
    
    @commands.command(hidden=True, aliases=['hof'])
    @is_admin()
    async def hall_of_fame(self, ctx: Context, channel='', react_num=10):
        '''
        Sets the hall of fame channel and number of reactions for this server. (Admin+)
        Arguments: channel (mention, name, or id), react_num (int)
        After [react_num] reactions with the :star2: emoji, messages will be shown in the hall of fame channel.
        '''
        increment_command_counter()

        if not ctx.guild:
            raise CommandError(message=f'Required argument missing: `guild`.')

        guild = await Guild.get(ctx.guild.id)

        if not channel:
            await guild.update(hall_of_fame_channel_id=None).apply()
            await ctx.send(f'Disabled hall of fame for this server.')
            return
        elif ctx.message.channel_mentions:
            channel = ctx.message.channel_mentions[0]
        else:
            found = False
            if is_int(channel):
                for c in ctx.guild.text_channels:
                    if c.id == int(channel):
                        channel = c
                        found = True
                        break
            if not found and isinstance(channel, str):
                for c in ctx.guild.text_channels:
                    if c.name.upper() == channel.upper():
                        channel = c
                        found = True
                        break
            if not found and isinstance(channel, str):
                for c in ctx.guild.text_channels:
                    if channel.upper() in c.name.upper():
                        channel = c
                        found = True
                        break
            if not found:
                raise CommandError(message=f'Could not find channel: `{channel}`.')
            
        if not isinstance(channel, discord.TextChannel):
            raise CommandError(message=f'Could not find channel: `{channel}`.')

        if react_num < 1:
            raise CommandError(message=f'Invalid argument: `react_num` (`{react_num}`). Must be at least 1.')

        await guild.update(hall_of_fame_channel_id=channel.id, hall_of_fame_react_num=react_num).apply()
        await ctx.send(f'Set the hall of fame channel for this server to {channel.mention}. The number of :star2: reactions required has been set to `{react_num}`.')

async def setup(bot: Bot):
    await bot.add_cog(ModCommands(bot))
