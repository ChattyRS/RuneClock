import asyncio
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from main import config_load, Guild, Role
from datetime import datetime

config = config_load()

months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

events_logged = 0

def log_event():
    global events_logged
    events_logged += 1

def get_events_logged():
    return events_logged

class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_command_error(self, ctx, error):
        if len(str(error).split('\"')) == 3:
            if str(error).split('\"')[0] == "Command " and str(error).split('\"')[2] == " is not found":
                return
        try:
            username = config['pc_username']
            error = str(error).replace(username, 'user')
            error = discord.utils.escape_mentions(error)
            msg = await ctx.send(error)
            await asyncio.sleep(10)
            await ctx.message.delete()
            await msg.delete()
        except:
            pass

    @Cog.listener()
    async def on_member_join(self, member):
        try:
            guild = await Guild.get(member.guild.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = member.guild.get_channel(guild.log_channel_id)
        if not channel:
            return
        log_event()
        title = f'**Member Joined**'
        colour = 0x00e400
        timestamp = datetime.utcnow()
        id = f'User ID: {member.id}'
        creation_time = member.created_at
        min = creation_time.minute
        if len(str(min)) == 1:
            min = '0' + str(min)
        hour = creation_time.hour
        time = f'{creation_time.day} {months[creation_time.month-1]} {creation_time.year}, {hour}:{min}'
        txt = (f'{member.mention} {member.name}#{member.discriminator}\n'
               f'Account creation: {time}')
        url = member.display_avatar.url
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        embed.set_thumbnail(url=url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return

    @Cog.listener()
    async def on_member_remove(self, member):
        try:
            guild = await Guild.get(member.guild.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = member.guild.get_channel(guild.log_channel_id)
        if not channel:
            return
        try:
            banlist = await member.guild.bans()
            for user in banlist:
                if user == member:
                    return
        except discord.Forbidden:
            pass
        log_event()
        title = f'**Member Left**'
        colour = 0xff0000
        timestamp = datetime.utcnow()
        id = f'User ID: {member.id}'
        txt = f'{member.mention} {member.name}#{member.discriminator}'
        url = member.display_avatar.url
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        embed.set_thumbnail(url=url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return

    @Cog.listener()
    async def on_member_ban(self, guild, user):
        try:
            g = await Guild.get(guild.id)
        except:
            return
        channel = None
        if g:
            if g.log_channel_id:
                channel = guild.get_channel(g.log_channel_id)
        if not channel:
            return
        log_event()
        title = f'**Member Banned**'
        colour = 0xff0000
        timestamp = datetime.utcnow()
        id = f'User ID: {user.id}'
        txt = f'{user.mention} {user.name}#{user.discriminator}'
        url = user.display_avatar.url
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        embed.set_thumbnail(url=url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return

    @Cog.listener()
    async def on_member_unban(self, guild, user):
        try:
            g = await Guild.get(guild.id)
        except:
            return
        channel = None
        if g:
            if g.log_channel_id:
                channel = guild.get_channel(g.log_channel_id)
        if not channel:
            return
        log_event()
        title = f'**Member Unbanned**'
        colour = 0xff7b1f
        timestamp = datetime.utcnow()
        id = f'User ID: {user.id}'
        txt = f'{user.name}#{user.discriminator}'
        url = user.display_avatar.url
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        embed.set_thumbnail(url=url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return

    @Cog.listener()
    async def on_message_delete(self, message):
        try:
            guild = await Guild.get(message.guild.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = message.guild.get_channel(guild.log_channel_id)
        if not channel:
            return
        if guild.log_bots == False and message.author.bot:
            return
        log_event()
        
        txt = (f'By: {message.author.mention} {message.author.name}#{message.author.discriminator}\n'
               f'In: {message.channel.mention}')
        embed = discord.Embed(title='**Message Deleted**', colour=0x00b2ff, timestamp=datetime.utcnow(), description=txt)
        msg = message.content
        if len(msg) > 1000:
            msg = msg[:1000] + '\n...'
        if not msg:
            msg = 'N/A'
        embed.add_field(name='Message', value=msg, inline=False)
        embed.set_footer(text=f'Message ID: {message.id}')
        embed.set_thumbnail(url=message.author.display_avatar.url)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return
    
    @Cog.listener()
    async def on_bulk_message_delete(self, messages):
        try:
            guild = await Guild.get(messages[0].guild.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = messages[0].guild.get_channel(guild.log_channel_id)
        if not channel:
            return
        log_event()

        txt = f'{len(messages)} messages deleted in {messages[0].channel.mention}'
        embed = discord.Embed(title='**Bulk delete**', colour=0x00b2ff, timestamp=datetime.utcnow(), description=txt)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return

    @Cog.listener()
    async def on_message_edit(self, before, after):
        try:
            guild = await Guild.get(after.guild.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = after.guild.get_channel(guild.log_channel_id)
        if not channel:
            return
        if guild.log_bots == False and after.author.bot:
            return

        member = after.author
        if member.bot or before.embeds or after.embeds: # don't log edits for bots or embeds
            return
        if after.content != before.content:
            log_event()
            title = f'**Message Edited**'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            id = f'Message ID: {after.id}'
            txt = (f'By: {member.mention} {member.name}#{member.discriminator}\n'
                   f'In: {after.channel.mention}')
            url = member.display_avatar.url
            beforeContent = before.content
            if not beforeContent:
                beforeContent = 'N/A'
            afterContent = after.content
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
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                return

    @Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if channel.guild is None:
            return
        try:
            guild = await Guild.get(channel.guild.id)
        except:
            return
        logChannel = None
        if guild:
            if guild.log_channel_id:
                logChannel = channel.guild.get_channel(guild.log_channel_id)
        if not logChannel:
            return
        log_event()
        title = f'**Channel Deleted**'
        colour = 0xff0000
        timestamp = datetime.utcnow()
        id = f'Channel ID: {channel.id}'
        creation_time = channel.created_at
        time = f'{creation_time.day} {months[creation_time.month-1]} {creation_time.year}, {creation_time.hour}:{creation_time.minute}'
        txt = (f'**{channel.name}** was deleted\n'
               f'Channel creation: {time}.')
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        try:
            await logChannel.send(embed=embed)
        except discord.Forbidden:
            return

    @Cog.listener()
    async def on_guild_channel_create(self, channel):
        if channel.guild is None:
            return
        try:
            guild = await Guild.get(channel.guild.id)
        except:
            return
        log_channel = None
        if guild:
            if guild.log_channel_id:
                log_channel = channel.guild.get_channel(guild.log_channel_id)
        if not log_channel:
            return
        log_event()
        title = f'**Channel Created**'
        colour = 0x00e400
        timestamp = datetime.utcnow()
        id = f'Channel ID: {channel.id}'
        txt = f'{channel.mention}'
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            return

    @Cog.listener()
    async def on_member_update(self, before, after):
        try:
            guild = await Guild.get(after.guild.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = after.guild.get_channel(guild.log_channel_id)
        if not channel:
            return

        if before.nick != after.nick:
            log_event()
            title = f'**Nickname Changed**'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            id = f'User ID: {after.id}'
            txt = f'{after.mention} {after.name}#{after.discriminator}'
            url = after.display_avatar.url
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            before_nick = before.nick
            if not before_nick:
                before_nick = 'N/A'
            after_nick = after.nick
            if not after_nick:
                after_nick = 'N/A'
            embed.add_field(name='Before', value=before_nick, inline=False)
            embed.add_field(name='After', value=after_nick, inline=False)
            embed.set_footer(text=id)
            embed.set_thumbnail(url=url)
            try:
                await channel.send(embed=embed)
                return
            except discord.Forbidden:
                return
        elif set(before.roles) != set(after.roles):
            log_event()
            added_roles = []
            removed_roles = []
            for r in before.roles:
                if not r in after.roles:
                    removed_roles.append(r)
            for r in after.roles:
                if not r in before.roles:
                    added_roles.append(r)
            title = f'**Roles Changed**'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            id = f'User ID: {after.id}'
            txt = f'{after.mention} {after.name}#{after.discriminator}'
            url = after.display_avatar.url
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            added = ""
            if added_roles:
                count = 0
                for role in added_roles:
                    count += 1
                    added += role.name
                    if count < len(added_roles):
                        added += ", "
                embed.add_field(name='Added', value=added, inline=False)
            removed = ""
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
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                return

    @Cog.listener()
    async def on_guild_update(self, before, after):
        try:
            guild = await Guild.get(after.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = after.get_channel(guild.log_channel_id)
        if not channel:
            return
        if before.name != after.name:
            log_event()
            owner = after.owner
            title = f'**Server Name Changed**'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            id = f'Server ID: {after.id}'
            txt = f'Owner: {owner.mention} {owner.name}#{owner.discriminator}'
            url = after.icon.url
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            before_name = before.name
            if not before_name:
                before_name = 'N/A'
            after_name = after.name
            if not after_name:
                after_name = 'N/A'
            embed.add_field(name='Before', value=before_name, inline=False)
            embed.add_field(name='After', value=after_name, inline=False)
            embed.set_footer(text=id)
            embed.set_thumbnail(url=url)
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                return

    @Cog.listener()
    async def on_guild_role_create(self, role):
        try:
            guild = await Guild.get(role.guild.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = role.guild.get_channel(guild.log_channel_id)
        if not channel:
            return
        log_event()
        title = f'**Role Created**'
        colour = 0x00e400
        timestamp = datetime.utcnow()
        id = f'Role ID: {role.id}'
        txt = f'{role.mention}'
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return
        '''
        TODO: state role permissions
        '''

    @Cog.listener()
    async def on_guild_role_delete(self, role):
        try:
            db_role = await Role.query.where(Role.guild_id==role.guild.id).where(Role.role_id==role.id).gino.first()
        except:
            return
        if db_role:
            await db_role.delete()
        try:
            guild = await Guild.get(role.guild.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = role.guild.get_channel(guild.log_channel_id)
        if not channel:
            return
        log_event()
        title = f'**Role Deleted**'
        colour = 0xff0000
        timestamp = datetime.utcnow()
        id = f'Role ID: {role.id}'
        txt = f'{role.name}'
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            return

    @Cog.listener()
    async def on_guild_role_update(self, before, after):
        try:
            guild = await Guild.get(after.guild.id)
        except:
            return
        channel = None
        if guild:
            if guild.log_channel_id:
                channel = after.guild.get_channel(guild.log_channel_id)
        if not channel:
            return
        if before.name != after.name:
            log_event()
            title = f'**Role Name Changed**'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            id = f'Role ID: {after.id}'
            txt = f'Role: {after.mention}'
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            embed.add_field(name='Before', value=before.name, inline=False)
            embed.add_field(name='After', value=after.name, inline=False)
            embed.set_footer(text=id)
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                return
        '''
        TODO: handle permission updates
        '''

    @Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        try:
            g = await Guild.get(guild.id)
        except:
            return
        channel = None
        if g:
            if g.log_channel_id:
                channel = guild.get_channel(g.log_channel_id)
        if not channel:
            return

        if len(before) != len(after):
            log_event()
            added = False
            new_emoji = None
            animated = False
            if len(before) > len(after):
                title = f'Emoji Deleted'
                for e in before:
                    if not e in after:
                        name = e.name
                        animated = e.animated
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
            timestamp = datetime.utcnow()
            id = f'Server ID: {guild.id}'
            txt = ''
            if added:
                try:
                    new_emoji_fetched = await guild.fetch_emoji(new_emoji.id)
                    txt = f'Added by {new_emoji_fetched.user.mention}:\n'
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
            try:
                await channel.send(embed=embed)
                return
            except discord.Forbidden:
                return
        before_names = []
        for e in before:
            before_names.append(e.name)
        after_names = []
        for e in after:
            after_names.append(e.name)
        old_name = ''
        new_name = ''
        for name in before_names:
            if not name in after_names:
                old_name = name
        for name in after_names:
            if not name in before_names:
                new_name = name
                for e in after:
                    if e.name == name:
                        afterEmoji = e
                        break
        if old_name and new_name:
            log_event()
            title = f'Emoji name changed'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            txt = f'Before: {old_name}\nAfter: {new_name}\n{str(afterEmoji)}'
            id = f'Server ID: {guild.id}'
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            embed.set_footer(text=id)
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                return

async def setup(bot):
    await bot.add_cog(Logs(bot))
