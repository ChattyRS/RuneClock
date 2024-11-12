import asyncio
from types import CodeType, ModuleType
from typing import Any, Callable, Mapping, NamedTuple, Sequence
from aiohttp import ClientResponse
import discord
from discord.ext import commands
from discord.ext.commands import Cog, Command as DiscordCommand
from github.AuthenticatedUser import AuthenticatedUser
from github.NamedUser import NamedUser
from github.Repository import Repository as GitRepository
from github.Commit import Commit
from gspread_asyncio import AsyncioGspreadClient, AsyncioGspreadSpreadsheet
from numpy import ndarray
from sqlalchemy import select, func
from src.bot import Bot
from src.database import Guild, Uptime, Command, Repository, RS3Item, OSRSItem, BannedGuild
from datetime import datetime, timedelta, UTC
import psutil
from pathlib import Path
import traceback
import textwrap
import inspect
from contextlib import redirect_stdout
import io
import itertools
from src.checks import is_owner, is_admin
from src.message_queue import QueueMessage
from src.number_utils import is_int
import matplotlib.pyplot as plt
from matplotlib.dates import date2num
import matplotlib.dates as mdates
from matplotlib.dates import DateFormatter
from src.date_utils import timedelta_to_string, uptime_fraction
from src.string_utils import remove_code_blocks
from src.exception_utils import format_syntax_error
from src.discord_utils import find_guild_text_channel, find_text_channel_by_name, get_custom_command, get_guild_text_channel, get_text_channel_by_name
from src.database_utils import find_custom_db_command, get_db_guild, find_osrs_item_by_id, get_osrs_item_by_id, find_rs3_item_by_id, get_rs3_item_by_id

class Management(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
        self.repl_session_channel_ids: set[int] = set()

        # Remove the default help command, as it will be replaced by a customized help command in this cog
        bot.remove_command('help')

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        '''
        Function to send welcome messages
        '''
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, member.guild)

        if not guild.welcome_message or not guild.welcome_channel_id:
            return
        
        welcome_channel: discord.TextChannel | None = find_guild_text_channel(member.guild, guild.welcome_channel_id)
        if not isinstance(welcome_channel, discord.TextChannel):
            return
        
        welcome_message: str = guild.welcome_message.replace('[user]', member.mention)
        welcome_message = welcome_message.replace('[server]', member.guild.name)

        self.bot.queue_message(QueueMessage(welcome_channel, welcome_message))

    @commands.command()
    async def help(self, ctx: commands.Context, command: str = '') -> None:
        '''
        This command.
        Give a command or command category as argument for more specific help.
        '''
        self.bot.increment_command_counter()
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, ctx.guild)

        extension: str | None = None

        if command:
            cmd: commands.Command | None = self.bot.get_command(command)
            custom_command: commands.Command = get_custom_command(self.bot)
            if not cmd:
                if not self.bot.get_cog(command):
                    raise commands.CommandError(message=f'Invalid argument: `{command}`.')
                else:
                    extension = command
            elif cmd == custom_command:
                async with self.bot.get_session() as session:
                    db_cmd: Command | None = await find_custom_db_command(session, ctx.guild, command)
                if not db_cmd:
                    raise commands.CommandError(message=f'Invalid argument: `{command}`.')
                alias_str: str = ' | '.join(db_cmd.aliases) if db_cmd.aliases else ''
                embed = discord.Embed(title=f'Help', description=f'`{command}`{alias_str}\n```{db_cmd.function}```\n{db_cmd.description}', colour=0x00e400, timestamp=datetime.now(UTC))
                embed.set_author(name=ctx.me.display_name, url=self.bot.config['github_link'], icon_url=ctx.me.display_avatar.url)
                embed.set_footer(text=f'You can change the description of your custom command using the command \"description\".')
                await ctx.send(embed=embed)
                await ctx.message.add_reaction('✅')
                return
            else:
                param_text: str = ' '.join([f'[{param}]' for param in cmd.clean_params])
                alias_str: str = ' | '.join(cmd.aliases) if cmd.aliases else ''
                embed = discord.Embed(title=f'Help', description=f'`{cmd.name}{alias_str} {param_text}`\n{cmd.help}', colour=0x00e400, timestamp=datetime.now(UTC))
                embed.set_author(name=f'{ctx.me.display_name}', url=self.bot.config['github_link'], icon_url=ctx.me.display_avatar.url)
                embed.set_footer(text=f'For more help, use the support command')
                await ctx.send(embed=embed)
                await ctx.message.add_reaction('✅')
                return

        embed = discord.Embed(title=f'Help', description=f'{self.bot.config["description"]}\nFor more detailed information about a specific command, use `help [command]`.', colour=0x00e400, url=self.bot.config['github_link'], timestamp=datetime.now(UTC))
        embed_short = discord.Embed(title=f'Help', description=f'{self.bot.config["description"]}\nFor more detailed information about a specific command, use `help [command]`.', colour=0x00e400, url=self.bot.config['github_link'], timestamp=datetime.now(UTC))

        embed.add_field(name='Prefix', value=f'My prefix in **{ctx.guild}** is currently set to `{guild.prefix}`. To change this, administrators can use the `prefix` command.')
        embed_short.add_field(name='Prefix', value=f'My prefix in **{ctx.guild}** is currently set to `{guild.prefix}`. To change this, administrators can use the `prefix` command.', inline=False)

        def predicate(cmd: commands.Command) -> bool:
            if ctx.author.id == self.bot.config['owner']:
                    return True
            elif cmd.hidden:
                return False

            if ctx.guild and ctx.guild.id == self.bot.config['portablesServer']:
                helper = False
                admin = False
                leader = False
                for role in ctx.author.roles if isinstance(ctx.author, discord.Member) else []:
                    if role.id == self.bot.config['helperRole']:
                        helper = True
                    elif role.id == self.bot.config['adminRole']:
                        admin = True
                    elif role.id == self.bot.config['leaderRole']:
                        leader = True
                if cmd.hidden and not ctx.author.id == self.bot.config['owner']:
                    return False
                if not leader and 'Leader+' in cmd.help if cmd.help else '':
                    return False
                if not admin and 'Admin+' in cmd.help if cmd.help else '':
                    return False
                if not helper and 'Helper+' in cmd.help if cmd.help else '':
                    return False
                return True
            else:
                if 'Portables only' in cmd.help if cmd.help else '':
                    return False
                elif 'Admin+' in cmd.help or 'Leader+' in cmd.help if cmd.help else '':
                    return isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator
                return True

        command_set: set[commands.Command] = self.bot.commands
        command_list: list[commands.Command] = [c for c in command_set if predicate(c)]
        command_list = sorted(command_list, key=lambda c: c.cog_name) # type: ignore

        for category, cmds in itertools.groupby(command_list, key=lambda x: x.cog_name):
            if not extension or isinstance(category, str) and category.upper() == extension.upper():
                cmds = list(cmds)
                if len(cmds) > 0:
                    val: str = ''
                    val_short: str = ''
                    for cmd in cmds:
                        param_text = ' '.join([f'[{param}]' for param in cmd.clean_params])
                        val += f'• `{(cmd.name + " " + param_text).strip()}`: {cmd.short_doc}\n'
                        val_short += f'• `{(cmd.name + " " + param_text).strip()}`\n'
                    val = val.strip()
                    val_short = val_short.strip()
                    if isinstance(category, str) and category.lower() == 'obliterate':
                        if ctx.guild and ctx.guild.id == self.bot.config['obliterate_guild_id'] or ctx.author.id == self.bot.config['owner']:
                            embed.add_field(name=f'{category}', value=val, inline=False)
                            embed_short.add_field(name=f'{category}', value=val_short, inline=False)
                    else:
                        embed.add_field(name=f'{category}', value=val, inline=False)
                        embed_short.add_field(name=f'{category}', value=val_short, inline=False)

        embed.set_author(name=f'{ctx.me.display_name}', url=self.bot.config['github_link'], icon_url=ctx.me.display_avatar.url)
        embed.set_footer(text=f'{len(self.bot.commands)} commands • {len(self.bot.extensions)} extensions')
        embed_short.set_author(name=f'{ctx.me.display_name}', url=self.bot.config['github_link'], icon_url=ctx.me.display_avatar.url)
        embed_short.set_footer(text=f'{len(self.bot.commands)} commands • {len(self.bot.extensions)} extensions')

        try:
            await ctx.author.send(embed=embed)
        except:
            await ctx.author.send(embed=embed_short)
        await ctx.message.add_reaction('✅')

    @commands.command(pass_context=True)
    @is_admin()
    async def welcome(self, ctx: commands.Context, channel_name: str = '', *msgParts) -> None:
        '''
        Changes server's welcome channel and message. (Admin+)
        Arguments: channel, message (optional).
        If no channel is given, welcome messages will no longer be sent.
        If no welcome message is given, default will be used:
        "Welcome to **[server]**, [user]!"
        [server] will be replaced by the name of your server.
        [user] will mention the user who joined.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')

        msg: str = ' '.join(msgParts)
        if not msg:
            msg = f'Welcome to **[server]**, [user]!'

        if ctx.message.channel_mentions:
            channel: discord.abc.GuildChannel | discord.Thread = ctx.message.channel_mentions[0]
        elif channel_name:
            channel = get_text_channel_by_name(ctx.guild, channel_name)
        else:
            async with self.bot.get_session() as session:
                guild: Guild = await get_db_guild(session, ctx.guild)
                if not guild.welcome_channel_id and not guild.welcome_message:
                    await ctx.send(f'Please mention the channel in which you would like to receive welcome messages.')
                    return
                guild.welcome_channel_id = None
                guild.welcome_message = None
                await session.commit()
                await ctx.send(f'I will no longer send welcome messages in server **{ctx.guild.name}**.')
                return

        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, ctx.guild)
            guild.welcome_channel_id = channel.id
            guild.welcome_message = msg
            await session.commit()

        await ctx.send(f'The welcome channel for server **{ctx.guild.name}** has been changed to {channel.mention}.\n'
                       f'The welcome message has been set to \"{msg}\".')

    @commands.command(pass_context=True, aliases=['servers', 'guilds', 'guildcount'])
    async def servercount(self, ctx: commands.Context) -> None:
        '''
        Returns the amount of servers that the bot is currently in.
        '''
        self.bot.increment_command_counter()
        await ctx.send(f'I am in **{len(self.bot.guilds)}** servers!')

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['logging'])
    @is_admin()
    async def log(self, ctx: commands.Context, channel_name: str = '') -> None:
        '''
        Changes server's logging channel. (Admin+)
        Arguments: channel.
        If no channel is given, logging messages will no longer be sent.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')

        if ctx.message.channel_mentions:
            channel: discord.abc.GuildChannel | discord.Thread = ctx.message.channel_mentions[0]
        elif channel_name:
            channel = get_text_channel_by_name(ctx.guild, channel_name)
        else:
            async with self.bot.get_session() as session:
                guild: Guild = await get_db_guild(session, ctx.guild)
                if not guild.log_channel_id:
                    await ctx.send(f'Please mention the channel in which you would like to receive logging messages.')
                    return
                guild.log_channel_id = None
                await session.commit()
                await ctx.send(f'I will no longer send logging messages in server **{ctx.guild.name}**.')
                return
        
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, ctx.guild)
            guild.log_channel_id = channel.id
            await session.commit()

        await ctx.send(f'The logging channel for server **{ctx.guild.name}** has been changed to {channel.mention}.')
    
    @log.command()
    @is_admin()
    async def bots(self, ctx: commands.Context) -> None:
        '''
        Toggles logging for bot messages.
        '''
        self.bot.increment_command_counter()

        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, ctx.guild)
            guild.log_bots = False if guild.log_bots else True
            await session.commit()
            await ctx.send(f'Bot message deletion and edit logging {"enabled" if guild.log_bots else "disabled"}.')


    @commands.command(pass_context=True)
    @is_admin()
    async def command(self, ctx: commands.Context, cmd: str = '') -> None:
        '''
        Disables/enables the given command for this server. (Admin+)
        '''
        self.bot.increment_command_counter()

        cmd = cmd.strip()
        if not cmd:
            raise commands.CommandError(message=f'Required argument missing: `command`.')
        elif cmd == 'command' or cmd == 'help':
            raise commands.CommandError(message=f'Invalid argument: `{cmd}`.')
        
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, ctx.guild)

            if guild.disabled_commands is None:
                guild.disabled_commands = [cmd]
                message: str = f'The command **{cmd}** has been **disabled**.'
            elif cmd in guild.disabled_commands:
                guild.disabled_commands = guild.disabled_commands.remove(cmd)
                message = f'The command **{cmd}** has been **enabled**.'
            else:
                guild.disabled_commands = guild.disabled_commands + [cmd]
                message = f'The command **{cmd}** has been **disabled**.'

            await session.commit()
            await ctx.send(message)

    @commands.command(pass_context=True, aliases=['setprefix'])
    @is_admin()
    async def prefix(self, ctx: commands.Context, prefix: str = '-') -> None:
        '''
        Changes server's command prefix (default "-"). (Admin+)
        Arguments: prefix
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')

        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, ctx.guild)
            guild.prefix = prefix
            await session.commit()
        
        await ctx.send(f'The command prefix for server **{ctx.guild.name}** has been set to `{prefix}`.')

    @commands.command(pass_context=True, aliases=['latency', 'delay'])
    async def ping(self, ctx: commands.Context) -> None:
        '''
        Pings the bot to check latency.
        '''
        self.bot.increment_command_counter()
        await ctx.send(f'`{int(self.bot.latency*1000)} ms`')
    
    @commands.command(aliases=['donate'])
    async def patreon(self, ctx: commands.Context) -> None:
        '''
        Provides a link to the RuneClock Patreon page where you can donate to help support ongoing development on RuneClock.
        '''
        self.bot.increment_command_counter()
        await ctx.send(f'You can support the hosting and ongoing development of RuneClock on Patreon here:\n{self.bot.config["patreon"]}')
    
    @commands.command(aliases=['server'])
    async def support(self, ctx: commands.Context) -> None:
        '''
        Provides an invite link to the RuneClock support server.
        '''
        self.bot.increment_command_counter()
        await ctx.send(self.bot.config['support_server'])

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['github'])
    async def git(self, ctx: commands.Context) -> None:
        '''
        Returns the link to the GitHub repository of this bot.
        '''
        self.bot.increment_command_counter()
        await ctx.send(f'**{ctx.me.display_name} on GitHub:**\n{self.bot.config["github_link"]}')
    
    @git.command()
    @is_admin()
    async def track(self, ctx: commands.Context, repo_url: str = '', channel_name: str = '') -> None:
        '''
        Receive notifications for updates to a GitHub repository in a channel.
        Arguments: GitHub repo url, channel
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')
        if not repo_url:
            raise commands.CommandError(message=f'Required argument missing: `repo_url`.')
        
        channel: discord.TextChannel | None = find_text_channel_by_name(ctx.guild, channel_name)
        channel = channel if channel else (ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None)
        if not channel:
            raise commands.CommandError(message=f'A text channel is required.')

        try:
            splits: list[str] = repo_url.split('/')
            user_name, repo_name = splits[len(splits)-2:len(splits)]
        except:
            raise commands.CommandError(message=f'Invalid repository URL: `{repo_url}`.')
        
        try:
            user: NamedUser | AuthenticatedUser = self.bot.github.get_user(user_name)
        except Exception as e:
            raise commands.CommandError(message=f'Could not find user: `{user_name}` {e}.')
        
        try:
            repo: GitRepository | None = next((r for r in user.get_repos() if r.name.upper() == repo_name.upper()), None)
        except:
            raise commands.CommandError(message=f'Could not find any repositories for user: `{user_name}`.')
        if not repo:
            raise commands.CommandError(message=f'Could not find a repository by the name: `{repo_name}`.')

        commit: Commit = repo.get_commits()[0]

        r: ClientResponse = await self.bot.aiohttp.get(commit.url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not fetch commit data.')
            data: Any = await r.json()

        async with self.bot.get_session() as session:
            if (await session.execute(select(Repository).where(Repository.guild_id == ctx.guild.id, Repository.user_name == user_name, Repository.repo_name == repo_name))).scalar_one_or_none():
                raise commands.CommandError(message=f'The repository `{repo_name}` is already being tracked.')
            
            session.add(Repository(guild_id=ctx.guild.id, channel_id=channel.id, user_name=user_name, repo_name=repo_name, sha=commit.sha))
            await session.commit()

        await ctx.send(f'The repository `{repo_name}` is now being tracked. Notifications for new commits will be sent to {channel.mention}.')

        embed = discord.Embed(
            title=f'{user_name}/{repo_name}', 
            colour=discord.Colour.blue(), 
            timestamp=datetime.strptime(data['commit']['author']['date'], "%Y-%m-%dT%H:%M:%SZ"), 
            description=f'[`{commit.sha[:7]}`]({commit.url}) {data["commit"]["message"]}\n{data["stats"]["additions"]} additions, {data["stats"]["deletions"]} deletions', 
            url=repo_url
        )
        embed.set_author(name=f'{data["commit"]["author"]["name"]}', url=f'{data["author"]["url"]}', icon_url=f'{data["author"]["avatar_url"]}')

        for file in data['files']:
            embed.add_field(name=file['filename'], value=f'{file["additions"]} additions, {file["deletions"]} deletions', inline=False)
        
        self.bot.queue_message(QueueMessage(channel, None, embed))
    
    @git.command()
    @is_admin()
    async def untrack(self, ctx: commands.Context, repo_url: str = '') -> None:
        '''
        Stop receiving notifications for updates to a GitHub repository in a channel.
        Arguments: GitHub repo url, channel
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')
        if not repo_url:
            raise commands.CommandError(message=f'Required argument missing: `repo_url`.')

        try:
            splits = repo_url.split('/')
            user_name, repo_name = splits[len(splits)-2:len(splits)]
        except:
            raise commands.CommandError(message=f'Invalid repository URL: `{repo_url}`.')
        
        async with self.bot.get_session() as session:
            repo: Repository | None = (await session.execute(select(Repository).where(Repository.guild_id == ctx.guild.id, Repository.user_name == user_name, Repository.repo_name == repo_name))).scalar_one_or_none()
            if repo:
                await session.delete(repo)
                await session.commit()
                await ctx.send(f'No longer tracking repository: `{repo_name}`.')
            else:
                raise commands.CommandError(message=f'Could not find any active trackers for the repository: `{repo_name}`.')

    @commands.command(aliases=['info'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def status(self, ctx: commands.Context) -> None:
        '''
        Returns the bot's current status.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        now: datetime = datetime.now(UTC).replace(microsecond=0)
        start_time: datetime = self.bot.start_time.replace(microsecond=0)
        delta: timedelta = now - start_time
        if delta < timedelta(minutes=1):
            pass
        elif delta < timedelta(hours=1):
            delta = now.replace(second=0) - start_time.replace(second=0)
        elif delta < timedelta(days=1):
            delta = now.replace(second=0, minute=0) - start_time.replace(second=0, minute=0)
        else:
            delta = now.replace(second=0, minute=0, hour=0) - start_time.replace(second=0, minute=0, hour=0)
        time: str = timedelta_to_string(delta)

        cpu_percent = str(psutil.cpu_percent(interval=None))
        ram: NamedTuple = psutil.virtual_memory() # total, available, percent, used, free, active, inactive, buffers, cached, shared, slab
        ram_percent: float = ram[2]
        disk_percent: float = psutil.disk_usage('/').percent
        txt: str = f'**OK**. :white_check_mark:\n**Shards:** {self.bot.shard_count}'

        try:
            agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
            ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
            await ss.worksheet('Home')
            gspread_status: str = f'Google API online'
        except:
            txt = '**Error**. :x:'
            gspread_status = f':x: Google API is down'
        extensions: Mapping[str, ModuleType] = self.bot.extensions
        cogs: list[str] = [x.stem for x in Path('cogs').glob('*.py')]
        cogs_txt: str = ''
        if len(extensions) < len(cogs):
            txt = '**Error**. :x:'
            cogs_txt += ':x: '
        cogs_txt += f'{len(extensions)}/{len(cogs)}'

        embed = discord.Embed(title='**Status**', colour=0x00e400, timestamp=now, description=txt)

        system: str = f'**CPU:** {cpu_percent}%\n**RAM:** {ram_percent}%\n**Disk:** {disk_percent}%'
        embed.add_field(name='__System__', value=system)

        info: str = f'**Extensions:** {cogs_txt}\n**Uptime:** {time}\n**Latency:** {int(self.bot.latency*1000)} ms'
        embed.add_field(name='__Info__', value=info)

        channels = 0
        users = 0
        for g in self.bot.guilds:
            channels += len(g.text_channels)
            users += g.member_count if g.member_count else 0

        connections = f'**Servers:** {len(self.bot.guilds)}\n**Channels:** {channels}\n**Users:** {users}'
        embed.add_field(name='__Connections__', value=connections)

        async with self.bot.get_session() as session:
            notification_channels: int | None = await session.scalar(select(func.count()).select_from(Guild).filter(Guild.notification_channel_id.is_not(None)))
            notification_channels = notification_channels if notification_channels else 0

        notifications: int = round(delta.total_seconds() / 3600 * 3.365 * notification_channels)
        processed = f'**Commands:** {self.bot.get_command_counter()}\n**Events:** {self.bot.events_logged}\n**Notifications:** {notifications}'
        embed.add_field(name='__Processed__', value=processed)

        embed.set_author(name='@schattie', url='https://github.com/ChattyRS/RuneClock', icon_url=self.bot.config['profile_picture_url'])

        embed.set_thumbnail(url=ctx.me.display_avatar.url)

        if not 'OK' in txt:
            embed.add_field(name='__Details__', value=f'{gspread_status}', inline=False)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    async def restart(self, ctx: commands.Context) -> None:
        '''
        Restarts the bot.
        '''
        try:
            await self.bot.close_database_connection()
        except:
            pass
        try:
            await ctx.send('OK, restarting...')
        except:
            print('Error sending restart message')
        self.bot.restart()

    @commands.command(pass_context=True)
    @is_admin()
    async def say(self, ctx: commands.Context) -> None:
        '''
        Makes the bot say something (Admin+).
        Arguments: channel_mention, message
        '''
        self.bot.increment_command_counter()
        channel = ctx.message.channel if not ctx.message.channel_mentions else ctx.message.channel_mentions[0]
        if not isinstance(channel, discord.TextChannel):
            raise commands.CommandError(message=f'Only text channels are supported')
        
        txt: str = ctx.message.content.replace(ctx.clean_prefix + "say", "", 1)
        txt = txt.replace(channel.mention, "", 1).strip()
        if not txt:
            raise commands.CommandError(message=f'Required argument missing: `message`.')
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(f'Missing permissions: `delete_message`.')

        await channel.send(txt)
    
    @commands.command(name='embed')
    @is_admin()
    async def _embed(self, ctx: commands.Context, title: str = 'Announcement', *message) -> None:
        '''
        Sends an embed. (Admin+)
        Arguments: title, channel (optional), message
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')

        channel = ctx.message.channel if not ctx.message.channel_mentions else ctx.message.channel_mentions[0]
        if not isinstance(channel, discord.TextChannel):
            raise commands.CommandError(message=f'Only text channels are supported')
        
        msg: str = ' '.join(message)
        if not msg:
            raise commands.CommandError(message=f'Required argument missing: `message`.')
        
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(f'Missing permissions: `delete_message`.')

        embed = discord.Embed(title=title, colour=0x00b2ff, timestamp=datetime.now(UTC), description=msg)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)

        await channel.send(embed=embed)
        

    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    async def eval(self, ctx: commands.Context, *, body: str = '') -> None:
        '''
        Evaluates code
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        env: dict[str, Any] = {
            'bot': self.bot,
            'config': self.bot.config,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
        }

        env.update(globals())

        body = str(body).strip()
        if not body:
            raise commands.CommandError(message=f'Required argument missing: `body`.')

        body = remove_code_blocks(body)
        stdout = io.StringIO()

        to_compile: str = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            raise commands.CommandError(message=f'Error:\n```py\n{e.__class__.__name__}: {e}\n```')

        func: Any = env['func']
        try:
            with redirect_stdout(stdout):
                ret: Any = await func()
        except Exception as e:
            value: str = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    await ctx.send(f'```py\n{value}\n```')
            else:
                await ctx.send(f'```py\n{value}{ret}\n```')

    @commands.command(hidden=True)
    @is_owner()
    async def load(self, ctx: commands.Context, *, module: str) -> None:
        '''
        Loads a module.
        '''
        self.bot.increment_command_counter()
        try:
            await self.bot.load_extension(f'cogs.{module}')
        except:
            raise commands.CommandError(message=f'Error:\n```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(f'Loaded extension: **{module}**')

    @commands.command(hidden=True)
    @is_owner()
    async def unload(self, ctx: commands.Context, *, module: str) -> None:
        '''
        Unloads a module.
        '''
        self.bot.increment_command_counter()
        try:
            await self.bot.unload_extension(f'cogs.{module}')
        except:
            raise commands.CommandError(message=f'Error:\n```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(f'Unloaded extension: **{module}**')

    @commands.command(hidden=True)
    @is_owner()
    async def reload(self, ctx: commands.Context, *, module: str) -> None:
        '''
        Reloads a module.
        '''
        self.bot.increment_command_counter()
        try:
            await self.bot.reload_extension(f'cogs.{module}')
        except:
            raise commands.CommandError(message=f'Error:\n```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(f'Reloaded extension: **{module}**')

    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    async def repl(self, ctx: commands.Context) -> None:
        """Launches an interactive REPL session."""
        self.bot.increment_command_counter()

        variables: dict[str, Any] = {
            'ctx': ctx,
            'bot': self.bot,
            'config': self.bot.config,
            'message': ctx.message,
            'guild': ctx.guild,
            'channel': ctx.channel,
            'author': ctx.author,
        }

        if ctx.channel.id in self.repl_session_channel_ids:
            raise commands.CommandError(message=f'Error: duplicate REPL session in `{ctx.channel}`.')

        self.repl_session_channel_ids.add(ctx.channel.id)
        await ctx.send('Enter code to execute or evaluate. `exit()` or `quit` to exit.')

        def check(m: discord.Message) -> bool:
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content.startswith('`')

        while True:
            try:
                response: discord.Message = await self.bot.wait_for('message', check=check, timeout=5.0 * 60.0)
            except asyncio.TimeoutError:
                await ctx.send('Exiting REPL session.')
                self.repl_session_channel_ids.remove(ctx.channel.id)
                break

            cleaned: str = remove_code_blocks(response.content)

            if cleaned in ('quit', 'exit', 'exit()'):
                await ctx.send('Exiting.')
                self.repl_session_channel_ids.remove(ctx.channel.id)
                return

            executor: Callable = exec
            code: CodeType | str = ''
            if cleaned.count('\n') == 0:
                # single statement, potentially 'eval'
                try:
                    code = compile(cleaned, '<repl session>', 'eval')
                except SyntaxError:
                    pass
                else:
                    executor = eval

            if executor is exec:
                try:
                    code = compile(cleaned, '<repl session>', 'exec')
                except SyntaxError as e:
                    await ctx.send(format_syntax_error(e))
                    continue

            variables['message'] = response

            fmt: str | None = None
            stdout = io.StringIO()

            try:
                with redirect_stdout(stdout):
                    result: Any = executor(code, variables)
                    if inspect.isawaitable(result):
                        result = await result
            except Exception as e:
                value: str = stdout.getvalue()
                fmt = f'```py\n{value}{traceback.format_exc()}\n```'
            else:
                value = stdout.getvalue()
                if result is not None:
                    fmt = f'```py\n{value}{result}\n```'
                    variables['_'] = result
                elif value:
                    fmt = f'```py\n{value}\n```'

            try:
                if fmt is not None:
                    if len(fmt) > 2000:
                        await ctx.send('Content too big to be printed.')
                    else:
                        await ctx.send(fmt)
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                raise commands.CommandError(message=f'Unexpected error: `{e}`')
    
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def uptime(self, ctx: commands.Context) -> None:
        '''
        Uptime statistics
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        now: datetime = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        async with self.bot.get_session() as session:
            events: Sequence[Uptime] = (await session.execute(select(Uptime).order_by(Uptime.time.asc()))).scalars().all()

        uptime_today: float = uptime_fraction(events, now.year, now.month, now.day)
        uptime_today_round: str = '{:.2f}'.format(uptime_today*100)

        uptime_month: float = uptime_fraction(events, now.year, now.month)
        uptime_month_round: str = '{:.2f}'.format(uptime_month*100)

        uptime_year: float = uptime_fraction(events, now.year)
        uptime_year_round: str = '{:.2f}'.format(uptime_year*100)

        uptime_lifetime: float = uptime_fraction(events)
        uptime_lifetime_round: str = '{:.2f}'.format(uptime_lifetime*100)

        loc = mdates.WeekdayLocator()

        formatter = DateFormatter('%d %b')

        plt.style.use('dark_background')

        fig, ax = plt.subplots()

        times: list[datetime] = []
        uptimes: list[float] = []
        for i in range(30):
            day: datetime = now - timedelta(days=i)
            times.append(day)
            uptimes.append(100 * uptime_fraction(events, day.year, day.month, day.day))

        dates: ndarray = date2num(times)
        plt.plot_date(dates, uptimes, color='#47a0ff', linestyle='-', ydate=False, xdate=True)

        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(formatter)

        ax.set_ylim(ymin=0, ymax=105)
        ax.yaxis.grid()

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)

        image = io.BytesIO()
        plt.savefig(image, transparent=True)
        plt.close(fig)
        image.seek(0)
        
        txt: str = f'Today: `{uptime_today_round}%`\nMonthly: `{uptime_month_round}%`\nYearly: `{uptime_year_round}%`\nLifetime: `{uptime_lifetime_round}%`'
        
        embed = discord.Embed(title='Uptime', colour=0x00b2ff, timestamp=datetime.now(UTC), description=txt)
        
        file = discord.File(image, filename='uptime.png')
        embed.set_image(url=f'attachment://uptime.png')

        await ctx.send(file=file, embed=embed)

    @commands.command()
    async def invite(self, ctx: commands.Context) -> None:
        '''
        Get an invite link to invite RuneClock to your servers.
        '''
        self.bot.increment_command_counter()
        url = 'https://discordapp.com/api/oauth2/authorize?client_id=449462150491275274&permissions=8&scope=bot%20applications.commands'
        await ctx.send(f'**RuneClock invite link:**\n{url}')
    
    @commands.command(hidden=True)
    @is_owner()
    async def add_item_osrs(self, ctx: commands.Context, id: int = 0) -> None:
        '''
        Add an item to the OSRS item database by ID.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not is_int(id):
            raise commands.CommandError(message=f'Required argument missing: `ID`.')
        id = int(id)
        async with self.bot.get_session() as session:
            item: OSRSItem | None = await find_osrs_item_by_id(session, id)
        if item:
            raise commands.CommandError(message=f'Item {item.name} with ID {item.id} is already in the database.')

        data_url: str = f'http://services.runescape.com/m=itemdb_oldschool/api/catalogue/detail.json?item={id}'
        graph_url: str = f'http://services.runescape.com/m=itemdb_oldschool/api/graph/{id}.json'
        item_data: Any = None
        graph_data: Any = None

        while not item_data and not graph_data:
            if not item_data:
                r: ClientResponse = await self.bot.aiohttp.get(data_url)
                async with r:
                    if r.status == 404:
                        raise commands.CommandError(message=f'Item with ID `{id}` does not exist.')
                    elif r.status != 200:
                        await asyncio.sleep(60)
                        continue
                    try:
                        item_data = await r.json(content_type='text/html')
                    except Exception as e:
                        raise commands.CommandError(message=f'Encountered exception:\n```{e}```')
            if not graph_data:
                r = await self.bot.aiohttp.get(graph_url)
                async with r:
                    if r.status == 404:
                        raise commands.CommandError(message=f'Item with ID `{id}` does not exist.')
                    elif r.status != 200:
                        await asyncio.sleep(60)
                        continue
                    try:
                        graph_data = await r.json(content_type='text/html')
                    except Exception as e:
                        raise commands.CommandError(message=f'Encountered exception:\n```{e}```')
        
        name: str = item_data['item']['name']
        icon_url: str = item_data['item']['icon_large']
        type: str = item_data['item']['type']
        description: str = item_data['item']['description']
        members: bool = True if item_data['item']['members'] == 'true' else False
        
        prices: list[str] = []
        for _, price in graph_data['daily'].items():
            prices.append(price)
        
        current: str = prices[len(prices) - 1]
        yesterday: str = prices[len(prices) - 2]
        month_ago: str = prices[len(prices) - 31]
        three_months_ago: str = prices[len(prices) - 91]
        half_year_ago: str = prices[0]

        today = str(int(current) - int(yesterday))
        day30: str = '{:.1f}'.format((int(current) - int(month_ago)) / int(month_ago) * 100) + '%'
        day90: str = '{:.1f}'.format((int(current) - int(three_months_ago)) / int(three_months_ago) * 100) + '%'
        day180: str = '{:.1f}'.format((int(current) - int(half_year_ago)) / int(half_year_ago) * 100) + '%'

        async with self.bot.get_session() as session:
            session.add(OSRSItem(id=int(id), name=name, icon_url=icon_url, type=type, description=description, members=members, current=str(current), today=str(today), day30=day30, day90=day90, day180=day180, graph_data=graph_data))
            await session.commit()

        await ctx.send(f'Item added: `{name}`: `{current}`.')
    
    @commands.command(hidden=True)
    @is_owner()
    async def remove_item_osrs(self, ctx: commands.Context, id: int = 0) -> None:
        '''
        Remove an item from the OSRS item database by ID.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not is_int(id):
            raise commands.CommandError(message=f'Required argument missing: `ID`.')
        id = int(id)
        async with self.bot.get_session() as session:
            item: OSRSItem = await get_osrs_item_by_id(session, id)
            await session.delete(item)
            await session.commit()

        await ctx.send(f'Item removed: `{id}`: `{item.name}`.')

    @commands.command(hidden=True)
    @is_owner()
    async def add_item_rs3(self, ctx: commands.Context, id: int = 0) -> None:
        '''
        Add an item to the RS3 item database by ID.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not is_int(id):
            raise commands.CommandError(message=f'Required argument missing: `ID`.')
        id = int(id)
        async with self.bot.get_session() as session:
            item: RS3Item | None = await find_rs3_item_by_id(session, id)
        if item:
            raise commands.CommandError(message=f'Item {item.name} with ID {item.id} is already in the database.')

        data_url: str = f'http://services.runescape.com/m=itemdb_rs/api/catalogue/detail.json?item={id}'
        graph_url: str = f'http://services.runescape.com/m=itemdb_rs/api/graph/{id}.json'
        item_data: Any = None
        graph_data: Any = None

        while not item_data and not graph_data:
            if not item_data:
                r: ClientResponse = await self.bot.aiohttp.get(data_url)
                async with r:
                    if r.status == 404:
                        raise commands.CommandError(message=f'Item with ID `{id}` does not exist.')
                    elif r.status != 200:
                        await asyncio.sleep(60)
                        continue
                    try:
                        item_data = await r.json(content_type='text/html')
                    except Exception as e:
                        raise commands.CommandError(message=f'Encountered exception:\n```{e}```')
            if not graph_data:
                r = await self.bot.aiohttp.get(graph_url)
                async with r:
                    if r.status == 404:
                        raise commands.CommandError(message=f'Item with ID `{id}` does not exist.')
                    elif r.status != 200:
                        await asyncio.sleep(60)
                        continue
                    try:
                        graph_data = await r.json(content_type='text/html')
                    except Exception as e:
                        raise commands.CommandError(message=f'Encountered exception:\n```{e}```')
        
        name: str = item_data['item']['name']
        icon_url: str = item_data['item']['icon_large']
        type: str = item_data['item']['type']
        description: str = item_data['item']['description']
        members: bool = True if item_data['item']['members'] == 'true' else False
        
        prices: list[str] = []
        for _, price in graph_data['daily'].items():
            prices.append(price)
        
        current: str = prices[len(prices) - 1]
        yesterday: str = prices[len(prices) - 2]
        month_ago: str = prices[len(prices) - 31]
        three_months_ago: str = prices[len(prices) - 91]
        half_year_ago: str = prices[0]

        today = str(int(current) - int(yesterday))
        day30: str = '{:.1f}'.format((int(current) - int(month_ago)) / int(month_ago) * 100) + '%'
        day90: str = '{:.1f}'.format((int(current) - int(three_months_ago)) / int(three_months_ago) * 100) + '%'
        day180: str = '{:.1f}'.format((int(current) - int(half_year_ago)) / int(half_year_ago) * 100) + '%'

        async with self.bot.get_session() as session:
            session.add(RS3Item(id=int(id), name=name, icon_url=icon_url, type=type, description=description, members=members, current=str(current), today=str(today), day30=day30, day90=day90, day180=day180, graph_data=graph_data))
            await session.commit()

        await ctx.send(f'Item added: `{name}`: `{current}`.')
    
    @commands.command(hidden=True)
    @is_owner()
    async def remove_item_rs3(self, ctx: commands.Context, id: int = 0) -> None:
        '''
        Remove an item from the RS3 item database by ID.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not is_int(id):
            raise commands.CommandError(message=f'Required argument missing: `ID`.')
        id = int(id)
        async with self.bot.get_session() as session:
            item: RS3Item = await get_rs3_item_by_id(session, id)
            await session.delete(item)
            await session.commit()

        await ctx.send(f'Item removed: `{id}`: `{item.name}`.')
    
    @commands.command(hidden=True)
    @is_owner()
    async def server_top(self, ctx: commands.Context) -> None:
        '''
        Return a list of the top-10 servers by size.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        guilds: list[discord.Guild] = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True) # type: ignore

        msg: str = '**Top 10 largest servers**'
        for i, guild in enumerate(guilds):
            msg += f'\n{guild.name}: `{guild.member_count}`'
            if i >= 9:
                break
        
        await ctx.send(msg)
    
    @commands.command(hidden=True)
    @is_owner()
    async def sim(self, ctx: commands.Context, key: str, val: str | int, command: str, *args) -> None:
        '''
        Debugging command to simulate a command being invoked from a different context.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild or not ctx.channel:
            raise commands.CommandError(message=f'This command can only be used from a server.')

        if not key:
            raise commands.CommandError(message=f'Required argument missing: \'key\'.')
        if not key in ['user', 'channel']:
            raise commands.CommandError(message=f'Invalid argument for \'key\': `{key}`.')
        
        if not val:
            raise commands.CommandError(message=f'Required argument missing: \'val\'.')
        if not is_int(val):
            raise commands.CommandError(message=f'Invalid argument for \'val\': `{val}`. Must be an integer ID.')
        val = int(val)

        if not command:
            raise commands.CommandError(message=f'Required argument missing: \'command\'.')
        cmd: DiscordCommand | None = self.bot.get_command(command)
        if not cmd:
            raise commands.CommandError(message=f'Command not found: `{command}`.')

        if key == 'user':
            user: discord.Member = await ctx.guild.fetch_member(val)
            ctx.author = user
            ctx.message.author = user
        elif key == 'channel':
            channel: discord.TextChannel = get_guild_text_channel(ctx.guild, val)
            ctx.channel = channel
            ctx.message.channel = channel
        
        ctx.message.content = command
        if args:
            ctx.message.content += " " + " ".join(args)
        
        ctx.invoked_with = command

        if await cmd.can_run(ctx):
            num_params: int = len(cmd.clean_params)
            if num_params >= len(args):
                await cmd.callback(self, ctx, *args) # type: ignore
            elif num_params == 0:
                await cmd.callback(ctx) # type: ignore
            else:
                args = args[:num_params]
                await cmd.callback(self, ctx, *args) # type: ignore
    
    @commands.command(hidden=True)
    @is_owner()
    async def sync(self, ctx: commands.Context, *guild_ids) -> None:
        '''
        Syncs application commands globally or to the given guild(s).
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if any(guild_ids):
            for guild_id in guild_ids:
                guild: discord.Guild | None = self.bot.get_guild(int(guild_id))
                if guild:
                    await self.bot.tree.sync(guild=guild)
                    await ctx.send(f'Synced application commands with guild: `{guild.name}`')
        else:
            await self.bot.tree.sync()
            await ctx.send(f'Synced application commands globally')

    @commands.command(hidden=True)
    @is_owner()
    async def ban_guild(self, ctx: commands.Context, guild_id: str | int, name: str = '', *reasons) -> None:
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not guild_id or not is_int(guild_id):
            raise commands.CommandError(message=f'Invalid argument \'guild_id\': `{guild_id}`.')
        guild_id = int(guild_id)
        async with self.bot.get_session() as session:
            banned_guild: BannedGuild | None = (await session.execute(select(BannedGuild).where(BannedGuild.id == guild_id))).scalar_one_or_none()
        if banned_guild:
            raise commands.CommandError(message=f'Guild {banned_guild.name} with ID `{guild_id}` is already banned.')
        reason: str = ' '.join(reasons)
        if not reason:
            reason = 'No reason given'

        guild: discord.Guild | None = self.bot.get_guild(guild_id)
        if guild:
            await guild.leave()
        
        async with self.bot.get_session() as session:
            session.add(BannedGuild(id=guild_id, name=name, reason=reason))
            await session.commit()

        await ctx.send(f'Banned guild `{name}` with ID `{guild_id}`.')

    @commands.command(hidden=True)
    @is_owner()
    async def unban_guild(self, ctx: commands.Context, guild_id: str | int) -> None:
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not guild_id or not is_int(guild_id):
            raise commands.CommandError(message=f'Invalid argument \'guild_id\': `{guild_id}`.')
        guild_id = int(guild_id)
        async with self.bot.get_session() as session:
            banned_guild: BannedGuild | None = (await session.execute(select(BannedGuild).where(BannedGuild.id == guild_id))).scalar_one_or_none()
            if not banned_guild:
                raise commands.CommandError(message=f'No banned guild found with ID `{guild_id}`.')
            await session.delete(banned_guild)
            await session.commit()
        
        await ctx.send(f'Guild `{banned_guild.name}` with ID `{guild_id}` has been unbanned.')

async def setup(bot: Bot) -> None:
    await bot.add_cog(Management(bot))
