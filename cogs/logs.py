import asyncio
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from main import config_load, Guild, Role
from datetime import datetime

config = config_load()

months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

eventsLogged = 0

def logEvent():
    global eventsLogged
    eventsLogged += 1

def getEventsLogged():
    return eventsLogged

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
        logEvent()
        title = f'**Member Joined**'
        colour = 0x00e400
        timestamp = datetime.utcnow()
        id = f'User ID: {member.id}'
        creationTime = member.created_at
        min = creationTime.minute
        if len(str(min)) == 1:
            min = '0' + str(min)
        hour = creationTime.hour
        time = f'{creationTime.day} {months[creationTime.month-1]} {creationTime.year}, {hour}:{min}'
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
        logEvent()
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
        logEvent()
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
        logEvent()
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
        logEvent()
        
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
        logEvent()

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
            logEvent()
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
        logEvent()
        title = f'**Channel Deleted**'
        colour = 0xff0000
        timestamp = datetime.utcnow()
        id = f'Channel ID: {channel.id}'
        creationTime = channel.created_at
        time = f'{creationTime.day} {months[creationTime.month-1]} {creationTime.year}, {creationTime.hour}:{creationTime.minute}'
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
        logEvent()
        title = f'**Channel Created**'
        colour = 0x00e400
        timestamp = datetime.utcnow()
        id = f'Channel ID: {channel.id}'
        txt = f'{channel.mention}'
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
        embed.set_footer(text=id)
        try:
            await logChannel.send(embed=embed)
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
            logEvent()
            title = f'**Nickname Changed**'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            id = f'User ID: {after.id}'
            txt = f'{after.mention} {after.name}#{after.discriminator}'
            url = after.display_avatar.url
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            beforeNick = before.nick
            if not beforeNick:
                beforeNick = 'N/A'
            afterNick = after.nick
            if not afterNick:
                afterNick = 'N/A'
            embed.add_field(name='Before', value=beforeNick, inline=False)
            embed.add_field(name='After', value=afterNick, inline=False)
            embed.set_footer(text=id)
            embed.set_thumbnail(url=url)
            try:
                await channel.send(embed=embed)
                return
            except discord.Forbidden:
                return
        elif set(before.roles) != set(after.roles):
            logEvent()
            addedRoles = []
            removedRoles = []
            for r in before.roles:
                if not r in after.roles:
                    removedRoles.append(r)
            for r in after.roles:
                if not r in before.roles:
                    addedRoles.append(r)
            title = f'**Roles Changed**'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            id = f'User ID: {after.id}'
            txt = f'{after.mention} {after.name}#{after.discriminator}'
            url = after.display_avatar.url
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            added = ""
            if addedRoles:
                count = 0
                for role in addedRoles:
                    count += 1
                    added += role.name
                    if count < len(addedRoles):
                        added += ", "
                embed.add_field(name='Added', value=added, inline=False)
            removed = ""
            if removedRoles:
                count = 0
                for role in removedRoles:
                    count += 1
                    removed += role.name
                    if count < len(removedRoles):
                        removed += ", "
                embed.add_field(name='Removed', value=removed, inline=False)
            embed.set_footer(text=id)
            embed.set_thumbnail(url=url)
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                return
            '''
            if after.guild == self.bot.get_guild(config['portablesServer']):
                for r in after.guild.roles:
                    if r.id == config['rankRole']:
                        rankRole = r
                if 'Smiley' in added and not 'Rank' in removed and not rankRole in before.roles:
                    smileyChannel = self.bot.get_channel(config['smileyChannel'])
                    locChannel = self.bot.get_channel(config['locChannel'])
                    msg = (f'Welcome to {smileyChannel.mention}, {after.mention}!\n'
                           f'Please use this channel for any FC related discussions, questions, and issues.\n\n'
                           f'Please check the pinned messages in this channel and in {locChannel.mention}, where you’ll be able to edit our sheets by updating locations, for important posts and details.')
                    try:
                        await smileyChannel.send(msg)
                    except discord.Forbidden:
                        return
                elif 'Rank' in added:
                    rankChannel = self.bot.get_channel(config['rankChannel'])
                    msg = (f'Welcome {after.mention}, and congratulations on your rank!\n'
                           f'If you have any questions, feel free to ask for help here in {rankChannel.mention}, or DM an Admin+.')
                    try:
                        await rankChannel.send(msg)
                    except discord.Forbidden:
                        return
                elif 'Moderator' in added and not 'Admin' in removed:
                    modChannel = self.bot.get_channel(config['modChannel'])
                    msg = (f'Welcome {after.mention}, and congratulations on your promotion!\n\n'
                           f'As a Moderator, you now have the ability to ban players from the FC. To do so, head over to the \'Bans\' tab on the sheets, and in a new row enter all the necessary information and set the status to \'Pending\'. Then send a message here in {modChannel.mention} along the lines of \"[player] to be banned\", and a Leader will apply the ban for you.\n\n'
                           f'If you have any questions, or if you\'re ever unsure about banning someone, feel free to discuss it here, or DM an Admin+ for advice.')
                    try:
                        await modChannel.send(msg)
                    except discord.Forbidden:
                        return
            '''

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
            logEvent()
            owner = after.owner
            title = f'**Server Name Changed**'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            id = f'Server ID: {after.id}'
            txt = f'Owner: {owner.mention} {owner.name}#{owner.discriminator}'
            url = after.icon.url
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            beforeName = before.name
            if not beforeName:
                beforeName = 'N/A'
            afterName = after.name
            if not afterName:
                afterName = 'N/A'
            embed.add_field(name='Before', value=beforeName, inline=False)
            embed.add_field(name='After', value=afterName, inline=False)
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
        logEvent()
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
        logEvent()
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
            logEvent()
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
            logEvent()
            added = False
            newEmoji = None
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
                        newEmoji = e
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
                    new_emoji_fetched = await guild.fetch_emoji(newEmoji.id)
                    txt = f'Added by {new_emoji_fetched.user.mention}:\n'
                except:
                    pass
                txt += f'{newEmoji} `{name}`\n'
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
        beforeNames = []
        for e in before:
            beforeNames.append(e.name)
        afterNames = []
        for e in after:
            afterNames.append(e.name)
        oldName = ''
        newName = ''
        for name in beforeNames:
            if not name in afterNames:
                oldName = name
        for name in afterNames:
            if not name in beforeNames:
                newName = name
                for e in after:
                    if e.name == name:
                        afterEmoji = e
                        break
        if oldName and newName:
            logEvent()
            title = f'Emoji name changed'
            colour = 0x00b2ff
            timestamp = datetime.utcnow()
            txt = f'Before: {oldName}\nAfter: {newName}\n{str(afterEmoji)}'
            id = f'Server ID: {guild.id}'
            embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)
            embed.set_footer(text=id)
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                return

def setup(bot):
    bot.add_cog(Logs(bot))
