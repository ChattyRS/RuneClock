import asyncio
import discord
from discord.ext import commands
import os
from sys import exit
from subprocess import call
import sys
sys.path.append('../')
from main import config_load, addCommand, Mute, Guild
from datetime import datetime, timedelta, timezone
import html
import re
from utils import timeDiffToString, is_int, RoleConverter
from utils import is_owner, is_admin, portables_admin, is_mod, is_rank, is_smiley, portables_only

config = config_load()

pattern = re.compile('[\W_]+')

def isName(memberName, member):
    name = member.display_name.upper()
    if memberName.upper() in pattern.sub('', name).upper():
        return True
    else:
        return False

class ModCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command()
    @is_admin()
    async def modmail(self, ctx, public='', private=''):
        '''
        Set up a public and private modmail channel. (Admin+)
        Any messages sent in the public channel will be instantly deleted and then copied to the private channel.
        To disable modmail, use this command without any arguments.
        Arguments:
        public: channel mention
        private: channel mention
        '''
        addCommand()

        if not public and not private:
            guild = await Guild.get(ctx.guild.id)
            await guild.update(modmail_public=None, modmail_private=None).apply()
            await ctx.send(f'Modmail has been disabled for server **{ctx.guild.name}**.')
            return

        if len(ctx.message.channel_mentions) < 2:
            raise commands.CommandError(message=f'Required arguments missing: 2 channel mentions required.')

        public, private = ctx.message.channel_mentions[0], ctx.message.channel_mentions[1]

        guild = await Guild.get(ctx.guild.id)

        await guild.update(modmail_public=public.id, modmail_private=private.id).apply()

        await ctx.send(f'Modmail public and private channels for server **{ctx.guild.name}** have been set to {public.mention} and {private.mention}.')
    
    @commands.Cog.listener()
    async def on_message(self, message):
        '''
        Modmail listener
        '''
        if message.author.bot:
            return
        if message.guild is None:
            return
        try:
            guild = await Guild.get(message.guild.id)
        except:
            return
        if guild:
            if not guild.modmail_public is None and not guild.modmail_private is None:
                if message.channel.id == guild.modmail_public:
                    embed = discord.Embed(description=f'In: {message.channel.mention}\n“{message.content}”', colour=0x00b2ff, timestamp=message.created_at)
                    embed.set_author(name=f'{message.author.display_name}#{message.author.discriminator}', icon_url=message.author.avatar_url)
                    embed.set_footer(text=f'ID: {message.id}')

                    txt = message.clean_content
                    author = message.author

                    await message.delete()

                    private = message.guild.get_channel(guild.modmail_private)
                    if private:
                        await private.send(embed=embed)
                    else:
                        await message.channel.send(f'Error: private modmail channel with ID `{guild.modmail_private}` not found.')
                    
                    '''
                    Cozy COTW nomination logging
                    '''
                    if guild.id == config['cozy_guild_id']:
                        agc = await self.bot.agcm.authorize()
                        ss = await agc.open_by_key(config['cozy_roster_key'])
                        roster = await ss.worksheet('Roster')

                        values = await roster.get_all_values()
                        values = values[1:]

                        author_name = ""
                        for value in values:
                            if value[5] == f'{author.name}#{author.discriminator}':
                                author_name = value[0]
                                break
                        if not author_name:
                            await private.send(f'This nomination has **not** been logged:\n```Could not find discord user: {author.name}#{author.discriminator}.```')
                            return
                        
                        nominees = []
                        for value in values:
                            if value[0].lower() in txt.lower():
                                nominees.append(value[0])
                        if not nominees:
                            await private.send(f'This nomination has **not** been logged:\n```Could not find nominees.```')
                            return

                        ss = await agc.open_by_key(config['cozy_cotw_nominations_key'])
                        nomination_sheet = await ss.worksheet('Nominations')

                        first_row = 1
                        col_values = await nomination_sheet.col_values(1)
                        first_row += len(col_values)

                        rows = []
                        for nominee in nominees:
                            rows.append([nominee, author_name, txt])
                        
                        await nomination_sheet.insert_rows(rows, first_row)

                        msg = 'Logged nominations:\n```'
                        msg += '\n'.join(nominees)
                        msg += '```'

                        await private.send(msg)


    @commands.command()
    @is_admin()
    async def mute(self, ctx, member='', duration='', reason='N/A'):
        '''
        Assigns a role 'Muted' to given member. (Admin+)
        Arguments:
        member: name, nickname, id, mention
        duration: [number][unit], where unit in {d, h, m} (optional)
        reason: string (optional)
        '''
        addCommand()
        await ctx.channel.trigger_typing()
        
        msg = ctx.message
        guild = ctx.guild

        if not member:
            raise commands.CommandError(message=f'Required argument missing: `member`.')

        temp = None
        if msg.mentions:
            temp = msg.mentions[0]
        if not temp:
            if is_int(member):
                temp = await guild.fetch_member(int(member))
        if not temp:
            temp = discord.utils.get(guild.members, display_name=member)
        if not temp:
            temp = discord.utils.get(guild.members, name=member)

        if not temp:
            raise commands.CommandError(message=f'Could not find member: `{member}`.')
        member = temp

        mute_role = discord.utils.find(lambda r: 'MUTE' in r.name.upper(), guild.roles)
        if not mute_role:
            try:
                mute_role = await guild.create_role(name='Muted', permissions=discord.Permissions.none())
            except discord.Forbidden:
                raise commands.CommandError(message=f'Missing permissions: `create_role`.')

        if mute_role in member.roles:
            raise commands.CommandError(message=f'Error: {member.mention} is already muted.')

        try:
            if not reason == 'N/A':
                await member.add_roles(mute_role, reason=reason)
            else:
                await member.add_roles(mute_role)
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `role_management`.')

        await ctx.send(f'{member.mention} has been **muted**.')

        if duration:
            # format: [num][unit] where unit in {d, h, m}
            temp = duration.replace(' ', '')
            units = ['d', 'h', 'm']
            input = []
            num = ''
            for char in temp:
                if not is_int(char) and not char.lower() in units:
                    raise commands.CommandError(message=f'Invalid argument: `duration`.')
                elif is_int(char):
                    num += char
                elif char.lower() in units:
                    if not num:
                        raise commands.CommandError(message=f'Invalid argument: `duration`.')
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
                raise commands.CommandError(message=f'Invalid argument: `duration`.')
            elif days*24*60 + hours*60 + minutes > 60*24*366:
                raise commands.CommandError(message=f'Invalid argument: `duration`.')
            duration = timedelta(days=days, hours=hours, minutes=minutes)

            end = str(datetime.utcnow().replace(second=0, microsecond=0) + duration)

            await Mute.create(guild_id=ctx.guild.id, user_id=member.id, expiration=end, reason=reason)

            await ctx.send(f'Mute expiration date set to: `{end}`.')

        for c in guild.text_channels:
            send = c.permissions_for(member).send_messages
            if not send:
                continue
            overwritten = False
            for o in c.overwrites:
                try:
                    obj = o[0]
                except:
                    obj = o
                if obj == mute_role:
                    overwritten = True
                    break
            if overwritten:
                o = c.overwrites_for(mute_role)
                if o.send_messages:
                    try:
                        await c.set_permissions(mute_role, send_messages=False)
                    except discord.Forbidden:
                        raise commands.CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')
            else:
                try:
                    await c.set_permissions(mute_role, send_messages=False)
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')
            send = c.permissions_for(member).send_messages
            if send:
                try:
                    await c.set_permissions(member, send_messages=False)
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')

    @commands.command()
    @is_admin()
    async def mutes(self, ctx):
        '''
        Get a list of temp mutes for this server. (Admin+)
        '''
        addCommand()

        msg = 'User ID             Expiration date      Reason'
        mutes = await Mute.query.where(Mute.guild_id==ctx.guild.id).gino.all()
        if not mutes:
            raise commands.CommandError(message=f'No mutes active.')
    
        for mute in mutes:
            msg += f'\n{mute.user_id}  {mute.expiration}  {mute.reason}'

        await ctx.send(f'```{msg}```')

    @commands.command()
    @is_admin()
    async def unmute(self, ctx, member):
        '''
        Unmute a member. (Admin+)
        member: name, nickname, id, mention
        '''
        addCommand()
        await ctx.channel.trigger_typing()
        
        msg = ctx.message
        guild = ctx.guild

        temp = None
        if msg.mentions:
            temp = msg.mentions[0]
        if not temp:
            if is_int(member):
                temp = await guild.fetch_member(int(member))
        if not temp:
            temp = discord.utils.get(guild.members, display_name=member)
        if not temp:
            temp = discord.utils.get(guild.members, name=member)

        if not temp:
            raise commands.CommandError(message=f'Could not find member: `{member}`.')
        member = temp

        mute_role = discord.utils.find(lambda r: 'MUTE' in r.name.upper(), guild.roles)
        if not mute_role:
            raise commands.CommandError(message=f'Missing role: `muted`.')

        if not mute_role in member.roles:
            raise commands.CommandError(message=f'Error: `{member.display_name}` is not muted.')
        else:
            try:
                await member.remove_roles(mute_role)
            except discord.Forbidden:
                raise commands.CommandError(message=f'Missing permissions: `role_management`.')
        
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
                        if member in c.overwrites:
                            overwrite = c.overwrites[member]
                            if overwrite[1].is_empty():
                                await c.set_permissions(member, overwrite=None)
                    except discord.Forbidden:
                        raise commands.CommandError(message=f'Missing permissions: `channel_permission_overwrites`.')

    @commands.command()
    @is_admin()
    async def kick(self, ctx, *, member: discord.Member):
        '''
        Kicks the given user (Admin+).
        Arguments: member
        '''
        addCommand()

        if member.top_role >= ctx.author.top_role and member.id != config['owner']:
            raise commands.CommandError(message=f'You have insufficient permissions to kick this user.')
        try:
            await member.kick()
        except discord.Forbidden:
            raise commands.CommandError(message=f'I have insufficient permissions to kick this user.')

        await ctx.send(f'`{member.display_name}` has been kicked.')

    @commands.command()
    @is_admin()
    async def ban(self, ctx, *, member: discord.Member):
        '''
        Bans the given user (Admin+).
        Arguments: member
        '''
        addCommand()

        if member.top_role >= ctx.author.top_role and member.id != config['owner']:
            raise commands.CommandError(message=f'You have insufficient permissions to ban this user.')
        try:
            await member.ban()
        except discord.Forbidden:
            raise commands.CommandError(message=f'I have insufficient permissions to ban this user.')

        await ctx.send(f'`{member.display_name}` has been banned.')

    @commands.command(pass_context=True, aliases=['delete', 'clear'])
    @is_admin()
    async def purge(self, ctx, num=0):
        '''
        Deletes given amount of messages (Admin+).
        Arguments: integer.
        Constraints: You can delete up to 100 messages at a time.
        '''
        addCommand()

        if not isinstance(num, int):
            if is_int(num):
                num = int(num)
            else:
                raise commands.CommandError(message=f'Invalid argument: `{num}`.')

        if not num or num < 1 or num > 100:
            raise commands.CommandError(message=f'Invalid argument: `{num}`.')
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
            raise commands.CommandError(message=f'Missing permissions: `delete_message`.')

    @commands.command(pass_context=True)
    @is_admin()
    async def role(self, ctx, role: RoleConverter, *, member: discord.Member):
        '''
        Toggles the given role for the given user (Admin+).
        Arguments: role, member
        '''
        addCommand()

        if member.top_role >= ctx.author.top_role and member.id != config['owner']:
            raise commands.CommandError(message=f'You have insufficient permissions to edit this user\'s roles.')
        if role > ctx.author.top_role and member.id != config['owner']:
            raise commands.CommandError(message=f'You have insufficient permissions to assign or remove this role.')

        if not role in member.roles:
            try:
                await member.add_roles(role)
                await ctx.send(f'**{member.display_name}** has been given role `{role.name}`.')
            except discord.Forbidden:
                raise commands.CommandError(message=f'I have insufficient permissions to assign this role to this user.')
        else:
            try:
                await member.remove_roles(role)
                await ctx.send(f'**{member.display_name}** has been removed from role `{role.name}`.')
            except discord.Forbidden:
                raise commands.CommandError(message=f'I have insufficient permissions to remove this role from this user.')

    @commands.command(pass_context=True, aliases=['promo'])
    @portables_admin()
    @portables_only()
    async def promote(self, ctx, *memberNames):
        '''
        Promotes the given user(s) (Admin+) (Portables only).
        Arguments: member(s)
        Members can be either one name or one or more mentions.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        msg = ctx.message
        user = ctx.author
        roles = user.roles
        guild = ctx.guild

        if len(msg.mentions) < 1 and not memberNames:
            raise commands.CommandError(message=f'Required argument missing: `user`.')

        members = msg.mentions
        if not members:
            if memberNames:
                memberName = ''
                for part in memberNames:
                    memberName += part + ' '
                memberName = memberName.strip()
                memberName = pattern.sub('', memberName).upper()
                member = discord.utils.find(lambda m: isName(memberName, m), guild.members)
                if not member:
                    raise commands.CommandError(message=f'Could not find user: `{memberName}`.')
                members.append(member)
        isLeader = False
        for r in roles:
            if r.id == config['leaderRole'] or user.id == config['owner']:
                isLeader = True
                break
        txt = ""
        for r in guild.roles:
            if r.id == config['smileyRole']:
                smileyRole = r
            if r.id == config['rankRole']:
                rankRole = r
            if r.id == config['editorRole']:
                editorRole = r
            if r.id == config['modRole']:
                modRole = r
            if r.id == config['adminRole']:
                adminRole = r
        for m in members:
            name = m.display_name
            if m.top_role < smileyRole:
                await m.add_roles(smileyRole)
                txt += f'**{name}** has been promoted to **Smiley**.\n'
            elif m.top_role < rankRole:
                await m.add_roles(rankRole, editorRole)
                txt += f'**{name}** has been promoted to **Editor**.\n'
            elif m.top_role < modRole:
                await m.add_roles(modRole)
                txt += f'**{name}** has been promoted to **Moderator**.\n'
            elif m.top_role < adminRole:
                if isLeader:
                    await m.add_roles(adminRole)
                    txt += f'**{name}** has been promoted to **Admin**.\n'
                else:
                    raise commands.CommandError(message=f'Missing permissions: `Admin`.')
            else:
                raise commands.CommandError(message=f'Missing permissions: `Admin`.')
        if txt:
            await ctx.send(txt)

    @commands.command(pass_context=True, aliases=['demo'])
    @portables_admin()
    @portables_only()
    async def demote(self, ctx, *memberNames):
        '''
        Demotes the given user(s) (Admin+) (Portables only).
        Arguments: member(s)
        Members can be either one name or one or more mentions.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        msg = ctx.message
        user = ctx.author
        roles = user.roles
        guild = ctx.guild

        if len(msg.mentions) < 1 and not memberNames:
            raise commands.CommandError(message=f'Required argument missing: `user`.')

        members = msg.mentions
        if not members:
            if memberNames:
                memberName = ''
                for part in memberNames:
                    memberName += part + ' '
                memberName = memberName.strip()
                memberName = pattern.sub('', memberName).upper()
                member = discord.utils.find(lambda m: isName(memberName, m), guild.members)
                if not member:
                    raise commands.CommandError(message=f'Could not find user: `{memberName}`.')
                members.append(member)

        isLeader = False
        for r in roles:
            if r.id == config['leaderRole'] or user.id == config['owner']:
                isLeader = True
                break

        txt = ""
        for r in guild.roles:
            if r.id == config['smileyRole']:
                smileyRole = r
            if r.id == config['vetRole']:
                vetRole = r
            if r.id == config['rankRole']:
                rankRole = r
            if r.id == config['editorRole']:
                editorRole = r
            if r.id == config['modRole']:
                modRole = r
            if r.id == config['adminRole']:
                adminRole = r
            if r.id == config['leaderRole']:
                leaderRole = r
        for m in members:
            roles = m.roles[1:] #get all except first role, because first role is always @everyone
            name = m.display_name
            if m.top_role >= leaderRole:
                raise commands.CommandError(message=f'Insufficient permissions.')
            elif m.top_role >= adminRole:
                if isLeader:
                    try:
                        await m.remove_roles(adminRole)
                        txt += f'**{name}** has been demoted to **Moderator**.\n'
                    except discord.Forbidden:
                        raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')
                else:
                    raise commands.CommandError(message=f'Missing permissions: `Admin`.')
            elif m.top_role >= modRole:
                try:
                    await m.remove_roles(modRole)
                    txt += f'**{name}** has been demoted to **Editor**.\n'
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')
            elif m.top_role >= rankRole:
                try:
                    await m.remove_roles(rankRole, editorRole)
                    txt += f'**{name}** has been demoted to **Smiley**.\n'
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')
            elif m.top_role >= smileyRole:
                try:
                    if vetRole in roles:
                        await m.remove_roles(smileyRole, vetRole)
                    else:
                        await m.remove_roles(smileyRole)
                    txt += f'**{name}** has been deranked.\n'
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')
            else:
                raise commands.CommandError(message=f'Error: `{name}` cannot be demoted any further.')
        if txt:
            await ctx.send(txt)

    @commands.command(pass_context=True)
    @portables_admin()
    @portables_only()
    async def derank(self, ctx, *memberNames):
        '''
        Deranks the given user(s) (Admin+) (Portables only).
        Arguments: members
        Members can be either one name or one or more mentions.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        msg = ctx.message
        user = ctx.author
        roles = user.roles
        guild = ctx.guild

        if len(msg.mentions) < 1 and not memberNames:
            raise commands.CommandError(message=f'Required argument missing: `user`.')

        members = msg.mentions
        if not members:
            if memberNames:
                memberName = ''
                for part in memberNames:
                    memberName += part + ' '
                memberName = memberName.strip()
                memberName = pattern.sub('', memberName).upper()
                member = discord.utils.find(lambda m: isName(memberName, m), guild.members)
                if not member:
                    raise commands.CommandError(message=f'Could not find user: `{memberName}`.')
                members.append(member)

        isLeader = False
        for r in roles:
            if r.id == config['leaderRole'] or user.id == config['owner']:
                isLeader = True
                break

        txt = ""
        for r in guild.roles:
            if r.id == config['smileyRole']:
                smileyRole = r
            if r.id == config['vetRole']:
                vetRole = r
            if r.id == config['rankRole']:
                rankRole = r
            if r.id == config['editorRole']:
                editorRole = r
            if r.id == config['modRole']:
                modRole = r
            if r.id == config['adminRole']:
                adminRole = r
            if r.id == config['leaderRole']:
                leaderRole = r
        for m in members:
            roles = m.roles[1:] #get all except first role, because first role is always @everyone
            name = m.display_name
            if m.top_role >= leaderRole:
                await ctx.send(f'Sorry, I do not have sufficient permissions to derank **{name}**.')
                raise commands.CommandError(message=f'Insufficient permissions.')
            elif m.top_role >= adminRole:
                if isLeader:
                    try:
                        await m.remove_roles(adminRole, modRole, editorRole, rankRole)
                        txt += f'{name} has been deranked.\n'
                    except discord.Forbidden:
                        raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')
                else:
                    raise commands.CommandError(message=f'Missing permissions: `Admin`.')
            elif m.top_role >= modRole:
                try:
                    await m.remove_roles(modRole, editorRole, rankRole)
                    txt += f'**{name}** has been deranked.\n'
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')
            elif m.top_role >= rankRole:
                try:
                    await m.remove_roles(editorRole, rankRole)
                    txt += f'**{name}** has been deranked.\n'
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')
            elif m.top_role >= smileyRole:
                try:
                    if vetRole in roles:
                        await m.remove_roles(smileyRole, vetRole)
                    else:
                        await m.remove_roles(smileyRole)
                    txt += f'**{name}** has been deranked.\n'
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')
            else:
                raise commands.CommandError(message=f'Error: `{name}` cannot be deranked any further.')
        if txt:
            await ctx.send(txt)

    @commands.command(pass_context=True, aliases=['mention'])
    @is_admin()
    async def mentionable(self, ctx, roleName=""):
        '''
        Toggles mentionable for the given role (Admin+).
        Arguments: role
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        guild = ctx.guild

        if not roleName:
            raise commands.CommandError(message=f'Required argument missing: `role`.')
        role = ""
        for r in guild.roles:
            if roleName.upper() == r.name.upper():
                role = r
                break
        if not role:
            for r in guild.roles:
                if roleName.upper() in r.name.upper():
                    role = r
                    break
        if not role:
            raise commands.CommandError(message=f'Could not find role: `{roleName}`.')
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
                raise commands.CommandError(message=f'Missing permissions: `edit_role`.')
            await ctx.send(f'{emoji}Role **{role.name}** has been made **{x}mentionable**.')

    @commands.command(pass_context=True)
    @portables_admin()
    @portables_only()
    async def accept(self, ctx):
        '''
        Accepts a smiley application (Admin+) (Portables only).
        Arguments: mention
        Constraints: Can only be used in the applications channel.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        msg = ctx.message
        author = ctx.author
        guild = ctx.guild
        channel = ctx.channel
        appChannel = self.bot.get_channel(config['applicationChannel'])

        if channel != appChannel:
            raise commands.CommandError(message=f'Incorrect channel.')

        if len(msg.mentions) != 1:
            raise commands.CommandError(message=f'Required argument missing: `user_mention`.')
        user = msg.mentions[0]
        role = discord.utils.get(guild.roles, name='Smiley')
        if role in user.roles:
            raise commands.CommandError(message=f'Error: `{user.display_name}` is already smilied.')
        smileyChannelID = config['smileyChannel']
        txt = f'Congratulations {user.mention}, \n\nYour application has been **accepted**. :white_check_mark: \nIf you have any questions, please do not hesitate to DM an admin or leader, or ask for help in <#{smileyChannelID}>. \n\nThank you for the help and welcome to the team! :slight_smile:'
        try:
            await ctx.send(txt)
            await user.add_roles(role)
            await msg.delete()
            adminChannel = self.bot.get_channel(config['adminChannel'])
            name = user.display_name
            await adminChannel.send(f'**{author.name}** has accepted **{name}**\'s smiley application.')
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions.')

    @commands.command(pass_context=True, aliases=['reject'])
    @portables_admin()
    @portables_only()
    async def decline(self, ctx):
        '''
        Declines a smiley application (Admin+) (Portables only).
        Arguments: mention
        Constraints: Can only be used in the applications channel.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        msg = ctx.message
        author = ctx.author
        channel = msg.channel
        appChannel = self.bot.get_channel(config['applicationChannel'])

        if channel != appChannel:
            raise commands.CommandError(message=f'Incorrect channel.')

        if len(msg.mentions) != 1:
            raise commands.CommandError(message=f'Required argument missing: `user_mention`.')

        user = msg.mentions[0]
        txt = f'Hi {user.mention}, \n\nUnfortunately, your application has been **declined**. :no_entry_sign: \nIf you have any questions, please do not hesitate to DM an admin or leader.'
        try:
            await ctx.send(txt)
            await msg.delete()
            adminChannel = self.bot.get_channel(config['adminChannel'])
            name = user.display_name
            await adminChannel.send(f'**{author.name}** has declined **{name}**\'s smiley application.')
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions.')

    @commands.command(pass_context=True, aliases=['rolecolor'])
    @is_admin()
    async def rolecolour(self, ctx, roleName="", colour=""):
        '''
        Changes the colour of the given role to the given colour (Admin+).
        Arguments: role, #hexcode
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not roleName or not colour:
            raise commands.CommandError(message=f'Required argument(s) missing: `role/colour`.')

        guild = ctx.guild
        roles = guild.roles
        roleExists = False
        role = False
        for r in roles:
            if r.name.upper() == roleName.upper():
                role = r
                roleExists = True
                break
        if not roleExists:
            raise commands.CommandError(message=f'Could not find role: `{roleName}`.')
        match = re.search(r'^#(?:[0-9a-fA-F]{3}){1,2}$', colour)
        if not match:
            raise commands.CommandError(message=f'Invalid argument: `{colour}`.')
        colour = colour.replace("#", "0x")
        colour = int(colour, 16)
        colour = discord.Colour(colour)
        user = ctx.author
        roles = user.roles
        try:
            await role.edit(colour=colour)
            await ctx.send(f'The colour for role **{role.name}** has been changed to **{str(colour)}**.')
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `edit_role`.')

    @commands.command(pass_context=True, aliases=['changenick', 'nick'])
    async def setnick(self, ctx, *userName):
        '''
        Changes the user's nickname.
        Arguments: nickname
        If no nickname is given, your nickname will be removed.
        Constraints: nickname must be a valid RSN
        '''
        addCommand()

        user = ctx.author
        input = ''
        for word in userName:
            input += word + ' '
        input = input.replace('_', ' ')
        input = input.strip()
        if not input:
            try:
                await user.edit(nick=None)
                await ctx.send(f'Your nickname has been removed.')
                return
            except discord.Forbidden:
                raise commands.CommandError(message=f'Missing permissions: `manage_nicknames`.')
        if len(input) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{input}`. Character limit exceeded.')
        if re.match('^[A-z0-9 -]+$', input) is None:
            raise commands.CommandError(message=f'Invalid argument: `{input}`. Forbidden character.')
        try:
            await user.edit(nick=input)
            await ctx.send(f'Your nickname has been changed to **{input}**.')
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `manage_nicknames`.')
    
    @commands.command()
    @is_admin()
    async def edit_nick(self, ctx, member: discord.Member, *nickname):
        '''
        Edits the nickname of the given user.
        '''
        nickname = ' '.join(nickname)
        if not nickname:
            raise commands.CommandError(message=f'Required argument missing: `nickname`.')
        try:
            await member.edit(nick=nickname)
            await ctx.send(f'`{member.name}`\'s nickname has been changed to `{nickname}`.')
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `manage_nicknames`. Or insufficient permissions to change {member.display_name}\'s nickname.')

    @commands.command(aliases=['delall'])
    @is_admin()
    async def deleteall(self, ctx, channel=''):
        '''
        Deletes all messages that will be sent in the given channel. (Admin+)
        Arguments: channel (mention, name, or id)
        '''
        addCommand()

        if not channel:
            raise commands.CommandError(message=f'Required argument missing: `channel`.')
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
            if not found:
                for c in ctx.guild.text_channels:
                    if c.name.upper() == channel.upper():
                        channel = c
                        found = True
                        break
            if not found:
                for c in ctx.guild.text_channels:
                    if channel.upper() in c.name.upper():
                        channel = c
                        found = True
                        break
            if not found:
                raise commands.CommandError(message=f'Could not find channel: `{channel}`.')

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
    async def hall_of_fame(self, ctx, channel='', react_num=10):
        '''
        Sets the hall of fame channel and number of reactions for this server. (Admin+)
        Arguments: channel (mention, name, or id), react_num (int)
        After [react_num] reactions with the :star2: emoji, messages will be shown in the hall of fame channel.
        '''
        addCommand()

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
            if not found:
                for c in ctx.guild.text_channels:
                    if c.name.upper() == channel.upper():
                        channel = c
                        found = True
                        break
            if not found:
                for c in ctx.guild.text_channels:
                    if channel.upper() in c.name.upper():
                        channel = c
                        found = True
                        break
            if not found:
                raise commands.CommandError(message=f'Could not find channel: `{channel}`.')

        if react_num < 1:
            raise commands.CommandError(message=f'Invalid argument: `react_num` (`{react_num}`). Must be at least 1.')

        await guild.update(hall_of_fame_channel_id=channel.id, hall_of_fame_react_num=react_num).apply()
        await ctx.send(f'Set the hall of fame channel for this server to {channel.mention}. The number of :star2: reactions required has been set to `{react_num}`.')

def setup(bot):
    bot.add_cog(ModCommands(bot))
