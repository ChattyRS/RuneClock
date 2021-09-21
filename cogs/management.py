import asyncio
import discord
from discord.ext import commands, tasks
import os
import sys
sys.path.append('../')
from main import config_load, addCommand, getCommandsAnswered, Guild, Uptime, Command, Repository, close_database, RS3Item, OSRSItem
from datetime import datetime, timedelta, timezone, date
import re
import psutil
from cogs.logs import getEventsLogged
from pathlib import Path
import wmi
import traceback
import textwrap
import inspect
from contextlib import redirect_stdout
import io
import copy
from typing import Union
import itertools
import utils
from utils import is_owner, is_admin, portables_admin, is_mod, is_rank, portables_only, is_int
from github import Github
import aiohttp
import matplotlib.pyplot as plt
from matplotlib.dates import date2num
import matplotlib.dates as mdates
from matplotlib.dates import DateFormatter
w = wmi.WMI(namespace="root\OpenHardwareMonitor", privileges=["Security"])

# to expose to the eval command
from collections import Counter

initialCpuUsage = psutil.cpu_percent(interval=None)

config = config_load()

g = Github(config['github_access_token'])

def restart():
    print("Restarting script...")
    os._exit(0)

def reboot():
    print('Rebooting...')
    os.system('shutdown -t 0 -r -f')

def pingToString(time):
    seconds = time.seconds
    microseconds = time.microseconds
    ms = seconds*1000 + int(microseconds/1000)
    time = str(ms) + ' ms'
    return time

def uptime_fraction(events, year=0, month=0, day=0):
    if day and month and year:
        today = date(year, month, day)
        if not any(event.time.date() == today for event in events):
            return 0
        elapsed = timedelta(hours=24)
        up = timedelta(seconds=0)
        start_time = datetime.utcnow().replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
        for i, event in enumerate(events):
            if event.time.year == year and event.time.month == month and event.time.day == day:
                if event.status == 'started':
                    start_time = event.time
                elif event.status == 'running':
                    up += event.time - start_time
            elif event.time > start_time:
                last_event = events[i-1]
                elapsed = last_event.time - datetime.utcnow().replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
                break
            if i == len(events) - 1:
                elapsed = event.time - datetime.utcnow().replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
        return up.total_seconds() / elapsed.total_seconds()
    elif year and month:
        start, end = None, None
        for i, event in enumerate(events):
            if event.time.year == year and event.time.month == month:
                if not start:
                    start = event.time
                end = event.time
            elif start and end:
                break
        percentages = []
        for day in range(start.day, end.day+1):
            percentages.append(uptime_fraction(events, year=year, month=month, day=day))
        return sum(percentages) / len(percentages)
    elif year:
        months = []
        for i, event in enumerate(events):
            if event.time.year == year:
                if not event.time.month in months:
                    months.append(event.time.month)
        percentages = []
        for month in months:
            percentages.append(uptime_fraction(events, year=year, month=month))
        return sum(percentages) / len(percentages)
    else:
        years = []
        for i, event in enumerate(events):
            if not event.time.year in years:
                years.append(event.time.year)
        percentages = []
        for year in years:
            percentages.append(uptime_fraction(events, year=year))
        return sum(percentages) / len(percentages)


class Management(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_result = None
        self.sessions = set()
        commands.Bot.remove_command(self.bot, 'help')
        self.uptime_tracking.start()
    
    def cog_unload(self):
        self.uptime_tracking.cancel()

    @tasks.loop(seconds=60)
    async def uptime_tracking(self):
        now = datetime.utcnow().replace(microsecond=0)
        today = now.replace(hour=0, minute=0, second=0)
        
        latest_event_today = await Uptime.query.where(Uptime.time >= today).order_by(Uptime.time.desc()).gino.first()
        if not latest_event_today:
            await Uptime.create(time=now, status='running')
            return

        if latest_event_today.status == 'running':
            await latest_event_today.update(time=now).apply()
        else:
            await Uptime.create(time=now, status='running')

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])
        # remove `foo`
        return content.strip('` \n')

    def get_syntax_error(self, e):
        if e.text is None:
            return f'```py\n{e.__class__.__name__}: {e}\n```'
        return f'```py\n{e.text}{"^":>{e.offset}}\n{e.__class__.__name__}: {e}```'

    @commands.command()
    async def help(self, ctx, command=''):
        '''
        This command.
        Give a command or command category as argument for more specific help.
        '''
        extension = ''
        if command:
            cmd = self.bot.get_command(command)
            custom_command = commands.Bot.get_command(self.bot, 'custom_command')
            if not cmd:
                if not self.bot.get_cog(command):
                    raise commands.CommandError(message=f'Invalid argument: `{command}`.')
                else:
                    extension = command
            elif cmd == custom_command:
                cmd = await Command.query.where(Command.guild_id==ctx.guild.id).where(Command.name==command).gino.first()
                if not cmd:
                    raise commands.CommandError(message=f'Invalid argument: `{command}`.')
                function = cmd.function
                aliases = cmd.aliases
                description = cmd.description
                alias_str = ''
                if aliases:
                    alias_str += ' | '
                    for i, alias in enumerate(aliases):
                        alias_str += f'`{alias}`'
                        if i < len(aliases)-1:
                            alias_str += ' | '
                embed = discord.Embed(title=f'Help', description=f'`{command}`{alias_str}\n```{function}```\n{description}', colour=0x00e400, timestamp=datetime.utcnow())
                embed.set_author(name=ctx.guild.me.display_name, url=config['github_link'], icon_url=ctx.guild.me.avatar_url)
                embed.set_footer(text=f'You can change the description of your custom command using the command \"description\".')
                await ctx.send(embed=embed)
                await ctx.message.add_reaction('✅')
                return
            else:
                params = cmd.clean_params
                param_text = ''
                for param in params:
                    param_text += f'[{param}] '
                param_text = param_text.strip()
                alias_str = ''
                if cmd.aliases:
                    alias_str += ' | '
                    for i, alias in enumerate(cmd.aliases):
                        alias_str += f'{alias}'
                        if i < len(cmd.aliases)-1:
                            alias_str += ' | '
                embed = discord.Embed(title=f'Help', description=f'`{cmd.name}{alias_str} {param_text}`\n{cmd.help}', colour=0x00e400, timestamp=datetime.utcnow())
                embed.set_author(name=f'{ctx.guild.me.display_name}', url=config['github_link'], icon_url=ctx.guild.me.avatar_url)
                embed.set_footer(text=f'For more help, feel free to DM me @ Chatty#0001', icon_url='https://i.imgur.com/HTs2ZZl.png')
                await ctx.send(embed=embed)
                await ctx.message.add_reaction('✅')
                return

        embed = discord.Embed(title=f'Help', description=f'{config["description"]}\nFor more detailed information about a specific command, use `help [command]`.', colour=0x00e400, url=config['github_link'], timestamp=datetime.utcnow())
        embed_short = discord.Embed(title=f'Help', description=f'{config["description"]}\nFor more detailed information about a specific command, use `help [command]`.', colour=0x00e400, url=config['github_link'], timestamp=datetime.utcnow())

        guild = await Guild.get(ctx.guild.id)
        guild_prefix = guild.prefix

        embed.add_field(name='Prefix', value=f'My prefix in **{ctx.guild.name}** is currently set to `{guild_prefix}`. To change this, administrators can use the `prefix` command.')
        embed_short.add_field(name='Prefix', value=f'My prefix in **{ctx.guild.name}** is currently set to `{guild_prefix}`. To change this, administrators can use the `prefix` command.', inline=False)

        def category(tup):
            cog = tup[1].cog_name
            return cog + ':' if cog is not None else '\u200bNo Category:'

        def predicate(cmd):
            if ctx.author.id == config['owner']:
                    return True
            elif cmd.hidden:
                return False

            if ctx.guild.id == config['portablesServer']:
                helper = False
                admin = False
                leader = False
                for role in ctx.author.roles:
                    if role.id == config['helperRole']:
                        helper = True
                    elif role.id == config['adminRole']:
                        admin = True
                    elif role.id == config['leaderRole']:
                        leader = True
                if cmd.hidden and not ctx.author.id == config['owner']:
                    return False
                if not leader and 'Leader+' in cmd.help:
                    return False
                if not admin and 'Admin+' in cmd.help:
                    return False
                if not helper and 'Helper+' in cmd.help:
                    return False
                return True
            else:
                if 'Portables only' in cmd.help:
                    return False
                elif 'Admin+' in cmd.help or 'Leader+' in cmd.help:
                    return ctx.author.guild_permissions.administrator
                return True

        command_list = self.bot.commands
        command_list = filter(predicate, command_list)
        command_list = sorted(command_list, key=lambda x: x.cog_name)

        for category, cmds in itertools.groupby(command_list, key=lambda x: x.cog_name):
            if category.upper() == extension.upper() or not extension:
                cmds = list(cmds)
                if len(cmds) > 0:
                    val = ''
                    val_short = ''
                    for command in cmds:
                        params = command.clean_params
                        param_text = ''
                        for param in params:
                            param_text += f'[{param}] '
                        param_text = param_text.strip()
                        val += f'• `{command.name} {param_text}`: {command.short_doc}\n'
                        val_short += f'• `{command.name} {param_text}`\n'
                    val = val.strip()
                    val_short = val_short.strip()
                    if category.upper() == 'COZY':
                        if ctx.guild.id == config['cozy_guild_id'] or ctx.author.id == config['owner']:
                            embed.add_field(name=f'{category}', value=val, inline=False)
                            embed_short.add_field(name=f'{category}', value=val_short, inline=False)
                    else:
                        embed.add_field(name=f'{category}', value=val, inline=False)
                        embed_short.add_field(name=f'{category}', value=val_short, inline=False)

        embed.set_author(name=f'{ctx.guild.me.display_name}', url=config['github_link'], icon_url='https://i.imgur.com/hu3nR8o.png')
        embed.set_footer(text=f'{len(self.bot.commands)} commands • {len(self.bot.extensions)} extensions')
        embed_short.set_author(name=f'{ctx.guild.me.display_name}', url=config['github_link'], icon_url='https://i.imgur.com/hu3nR8o.png')
        embed_short.set_footer(text=f'{len(self.bot.commands)} commands • {len(self.bot.extensions)} extensions')

        try:
            await ctx.author.send(embed=embed)
        except:
            await ctx.author.send(embed=embed_short)
        await ctx.message.add_reaction('✅')

    @commands.command(pass_context=True)
    @is_admin()
    async def welcome(self, ctx, channel='', *msgParts):
        '''
        Changes server's welcome channel and message. (Admin+)
        Arguments: channel, message (optional).
        If no channel is given, welcome messages will no longer be sent.
        If no welcome message is given, default will be used:
        "Welcome to **[server]**, [user]!"
        [server] will be replaced by the name of your server.
        [user] will mention the user who joined.
        '''
        addCommand()

        msg = ' '.join(msgParts)
        if not msg:
            msg = f'Welcome to **[server]**, [user]!'

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
                raise commands.CommandError(message=f'Missing channel: `{channel}`.')
        else:
            guild = await Guild.get(ctx.guild.id)
            if not guild.welcome_channel_id and not guild.welcome_message:
                await ctx.send(f'Please mention the channel in which you would like to receive welcome messages.')
                return
            await guild.update(welcome_channel_id=None).apply()
            await guild.update(welcome_message=None).apply()
            await ctx.send(f'I will no longer send welcome messages in server **{ctx.guild.name}**.')
            return

        guild = await Guild.get(ctx.guild.id)
        await guild.update(welcome_channel_id=channel.id).apply()
        await guild.update(welcome_message=msg).apply()

        await ctx.send(f'The welcome channel for server **{ctx.guild.name}** has been changed to {channel.mention}.\n'
                       f'The welcome message has been set to \"{msg}\".')

    @commands.command(pass_context=True, aliases=['servers', 'guilds', 'guildcount'])
    async def servercount(self, ctx):
        '''
        Returns the amount of servers that the bot is currently in.
        '''
        addCommand()
        await ctx.send(f'I am in **{len(self.bot.guilds)}** servers!')

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['logging'])
    @is_admin()
    async def log(self, ctx, channel=''):
        '''
        Changes server's logging channel. (Admin+)
        Arguments: channel.
        If no channel is given, logging messages will no longer be sent.
        '''
        addCommand()

        if ctx.message.channel_mentions:
            channel = ctx.message.channel_mentions[0]
        elif channel:
            found = False
            for c in ctx.guild.channels:
                if channel.upper() == c.name.upper():
                    channel = c
                    found = True
                    break
            if not found:
                for c in ctx.guild.channels:
                    if channel.upper() in c.name.upper():
                        channel = c
                        found = True
                        break
            if not found:
                raise commands.CommandError(message=f'Missing channel: `{channel}`.')
        else:
            guild = await Guild.get(ctx.guild.id)
            if not guild.log_channel_id:
                await ctx.send(f'Please mention the channel in which you would like to receive logging messages.')
                return
            await guild.update(log_channel_id=None).apply()
            await ctx.send(f'I will no longer send logging messages in server **{ctx.guild.name}**.')
            return
        
        guild = await Guild.get(ctx.guild.id)
        await guild.update(log_channel_id=channel.id).apply()

        await ctx.send(f'The logging channel for server **{ctx.guild.name}** has been changed to {channel.mention}.')
    
    @log.command()
    @is_admin()
    async def bots(self, ctx):
        '''
        Toggles logging for bot messages.
        '''
        addCommand()

        guild = await Guild.get(ctx.guild.id)
        new_val = False if guild.log_bots is None or guild.log_bots == True else True
        await guild.update(log_bots=new_val).apply()

        await ctx.send(f'Bot message deletion and edit logging {"enabled" if new_val else "disabled"}.')


    @commands.command(pass_context=True)
    @is_admin()
    async def command(self, ctx, cmd=''):
        '''
        Disables/enables the given command for this server. (Admin+)
        '''
        addCommand()

        cmd = cmd.strip()
        if not cmd:
            raise commands.CommandError(message=f'Required argument missing: `command`.')
        elif cmd == 'command' or cmd == 'help':
            raise commands.CommandError(message=f'Invalid argument: `{cmd}`.')
        
        guild = await Guild.get(ctx.guild.id)
        if guild.disabled_commands is None:
            await guild.update(disabled_commands=[cmd]).apply()
            try:
                await ctx.send(f'The command **{cmd}** has been **disabled**.')
            except discord.Forbidden:
                pass
        elif cmd in guild.disabled_commands:
            await guild.update(disabled_commands = guild.disabled_commands.remove(cmd)).apply()
            try:
                await ctx.send(f'The command **{cmd}** has been **enabled**.')
            except discord.Forbidden:
                pass
        else:
            await guild.update(disabled_commands = guild.disabled_commands + [cmd]).apply()
            try:
                await ctx.send(f'The command **{cmd}** has been **disabled**.')
            except discord.Forbidden:
                pass

    @commands.command(pass_context=True, aliases=['setprefix'])
    @is_admin()
    async def prefix(self, ctx, prefix='-'):
        '''
        Changes server's command prefix (default "-"). (Admin+)
        Arguments: prefix
        '''
        addCommand()

        guild = await Guild.get(ctx.guild.id)
        await guild.update(prefix=prefix).apply()
        
        await ctx.send(f'The command prefix for server **{ctx.guild.name}** has been set to `{prefix}`.')

    @commands.command(pass_context=True, aliases=['latency', 'delay'])
    async def ping(self, ctx):
        '''
        Pings the bot to check latency.
        '''
        addCommand()
        await ctx.send(f'`{int(self.bot.latency*1000)} ms`')
    
    @commands.command(aliases=['donate'])
    async def patreon(self, ctx):
        '''
        Provides a link to the RuneClock Patreon page where you can donate to help support ongoing development on RuneClock.
        '''
        addCommand()
        await ctx.send(f'You can support the hosting and ongoing development of RuneClock on Patreon here:\n{config["patreon"]}')
    
    @commands.command(aliases=['server'])
    async def support(self, ctx):
        '''
        Provides an invite link to the RuneClock support server.
        '''
        addCommand()
        await ctx.send(config['support_server'])

    @commands.group(pass_context=True, invoke_without_command=True, aliases=['github'])
    async def git(self, ctx):
        '''
        Returns the link to the GitHub repository of this bot.
        '''
        addCommand()
        name = ctx.guild.me.display_name
        await ctx.send(f'**{name} on GitHub:**\n{config["github_link"]}')
    
    @git.command()
    @is_admin()
    async def track(self, ctx, repo_url='', channel=''):
        '''
        Receive notifications for updates to a GitHub repository in a channel.
        Arguments: GitHub repo url, channel
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not repo_url:
            raise commands.CommandError(message=f'Required argument missing: `repo_url`.')
        
        # Get channel
        if channel:
            if ctx.message.channel_mentions:
                channel = ctx.message.channel_mentions[0]
            else:
                channel = discord.utils.get(ctx.guild.channels, name=channel)
                if not channel:
                    channel = ctx.channel
        else:
            channel = ctx.channel

        try:
            splits = repo_url.split('/')
            user_name, repo_name = splits[len(splits)-2:len(splits)]
        except:
            raise commands.CommandError(message=f'Invalid repository URL: `{repo_url}`.')
        
        try:
            user = g.get_user(user_name)
            if not user:
                raise commands.CommandError(message=f'Could not find user: `{user_name}`.')
        except:
            raise commands.CommandError(message=f'Could not find user: `{user_name}`.')
        
        try:
            repos = user.get_repos()
            if not repos:
                raise commands.CommandError(message=f'Could not find any repositories for user: `{user_name}`.')
        except:
            raise commands.CommandError(message=f'Could not find any repositories for user: `{user_name}`.')
        
        num_repos = 0
        for repo in repos:
            num_repos += 1

        for i, repo in enumerate(repos):
            if repo.name.upper() == repo_name.upper():
                break
            elif i == num_repos - 1:
                raise commands.CommandError(message=f'Could not find a repository by the name: `{repo_name}`.')

        commits = repo.get_commits()
        
        for i, commit in enumerate(commits):
            commit_url = commit.url
            break

        r = await self.bot.aiohttp.get(commit_url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not fetch commit data.')
            data = await r.json()

        repository = Repository(guild_id=ctx.guild.id, channel_id=channel.id, user_name=user_name, repo_name=repo_name, sha=commit.sha)

        repositories = await Repository.query.where(Repository.guild_id==ctx.guild.id).gino.all()
        for r in repositories:
            if r.user_name == user_name and r.repo_name == repo_name:
                raise commands.CommandError(message=f'The repository `{repo_name}` is already being tracked.')

        repository = await Repository.create(guild_id=ctx.guild.id, channel_id=channel.id, user_name=user_name, repo_name=repo_name, sha=commit.sha)

        await ctx.send(f'The repository `{repo_name}` is now being tracked. Notifications for new commits will be sent to {channel.mention}.')

        embed = discord.Embed(title=f'{user_name}/{repo_name}', colour=discord.Colour.blue(), timestamp=datetime.strptime(data['commit']['author']['date'], "%Y-%m-%dT%H:%M:%SZ"), description=f'[`{commit.sha[:7]}`]({commit_url}) {data["commit"]["message"]}\n{data["stats"]["additions"]} additions, {data["stats"]["deletions"]} deletions', url=repo_url)
        embed.set_author(name=f'{data["commit"]["author"]["name"]}', url=f'{data["author"]["url"]}', icon_url=f'{data["author"]["avatar_url"]}')

        for file in data['files']:
            embed.add_field(name=file['filename'], value=f'{file["additions"]} additions, {file["deletions"]} deletions', inline=False)
        
        await channel.send(embed=embed)
    
    @git.command()
    @is_admin()
    async def untrack(self, ctx, repo_url=''):
        '''
        Stop receiving notifications for updates to a GitHub repository in a channel.
        Arguments: GitHub repo url, channel
        '''
        addCommand()

        if not repo_url:
            raise commands.CommandError(message=f'Required argument missing: `repo_url`.')

        try:
            splits = repo_url.split('/')
            user_name, repo_name = splits[len(splits)-2:len(splits)]
        except:
            raise commands.CommandError(message=f'Invalid repository URL: `{repo_url}`.')
        
        repositories = await Repository.query.where(Repository.guild_id==ctx.guild.id).gino.all()
        for r in repositories:
            if r.user_name == user_name and r.repo_name == repo_name:
                await r.delete()
                await ctx.send(f'No longer tracking repository: `{repo_name}`.')
                return
        
        raise commands.CommandError(message=f'Could not find any active trackers for the repository: `{repo_name}`.')

    @commands.command(aliases=['info'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def status(self, ctx):
        '''
        Returns the bot's current status.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        now = datetime.utcnow()
        time = now.replace(microsecond=0)
        start_time = self.bot.start_time
        delta = time - start_time.replace(microsecond=0)
        if delta < timedelta(minutes=1):
            time = delta
        elif delta < timedelta(hours=1):
            time = now.replace(microsecond=0, second=0)
            time -= start_time.replace(microsecond=0, second=0)
        elif delta < timedelta(days=1):
            time = now.replace(microsecond=0, second=0, minute=0)
            time -= start_time.replace(microsecond=0, second=0, minute=0)
        else:
            time = now.replace(microsecond=0, second=0, minute=0, hour=0)
            time -= start_time.replace(microsecond=0, second=0, minute=0, hour=0)
        delta = time
        time = utils.timeDiffToString(time)
        cpuPercent = str(psutil.cpu_percent(interval=None))
        ram = psutil.virtual_memory() # total, available, percent, used, free, active, inactive, buffers, cached, shared, slab
        ramPercent = ram[2]
        title = f'**Status**'
        colour = 0x00e400
        timestamp = datetime.utcnow()
        txt = f'**OK**. :white_check_mark:'
        txt += f'\n**Shards:** {self.bot.shard_count}'

        try:
            agc = await self.bot.agcm.authorize()
            ss = await agc.open(config['sheetName'])
            await ss.worksheet('Home')
            gspread_status = f'Google API online'
        except:
            txt = '**Error**. :x:'
            gspread_status = f':x: Google API is down'
        extensions = self.bot.extensions
        cogs = [x.stem for x in Path('cogs').glob('*.py')]
        cogs_txt = ''
        if len(extensions) < len(cogs):
            txt = '**Error**. :x:'
            cogs_txt += ':x: '
        cogs_txt += f'{len(extensions)}/{len(cogs)}'

        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp, description=txt)

        temp = 20
        temperature_info = w.Sensor()
        for sensor in temperature_info:
            if sensor.SensorType == 'Temperature':
                if sensor.Name == 'CPU Package':
                    temp = str(sensor.Value).replace('.0', '')
                    break


        system = f'**CPU:** {cpuPercent}%\n**RAM:** {ramPercent}%\n**Temp:** {temp}°C'
        embed.add_field(name='__System__', value=system)

        info = f'**Extensions:** {cogs_txt}\n**Uptime:** {time}\n**Latency:** {int(self.bot.latency*1000)} ms'
        embed.add_field(name='__Info__', value=info)

        channels = 0
        users = 0
        for g in self.bot.guilds:
            channels += len(g.text_channels)
            users += g.member_count

        connections = f'**Servers:** {len(self.bot.guilds)}\n**Channels:** {channels}\n**Users:** {users}'
        embed.add_field(name='__Connections__', value=connections)

        notification_channels = 0
        guilds = await Guild.query.gino.all()
        for guild in guilds:
            if guild.notification_channel_id:
                notification_channels += 1

        notifications = round(delta.total_seconds() / 3600 * 3.365 * notification_channels)
        processed = f'**Commands:** {getCommandsAnswered()}\n**Events:** {getEventsLogged()}\n**Notifications:** {notifications}'
        embed.add_field(name='__Processed__', value=processed)

        embed.set_author(name='Chatty#0001', url='https://github.com/ChattyRS/Portables', icon_url='https://i.imgur.com/y1ovBqC.png')

        embed.set_thumbnail(url='https://i.imgur.com/Hccdnts.png')

        if not 'OK' in txt:
            embed.add_field(name='__Details__', value=f'{gspread_status}', inline=False)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    async def restart(self, ctx):
        '''
        Restarts the bot.
        '''
        try:
            await close_database()
        except:
            pass
        try:
            await ctx.send('OK, restarting...')
        except:
            print('Error sending restart message')
        restart()
    
    @commands.command(hidden=True)
    @is_owner()
    async def reboot(self, ctx):
        '''
        Restarts the system.
        '''
        try:
            await close_database()
        except:
            pass
        try:
            await ctx.send('OK, restarting the system...')
        except:
            print('Error sending restart message')
        reboot()

    @commands.command(pass_context=True)
    @is_admin()
    async def say(self, ctx):
        '''
        Makes the bot say something (Admin+).
        Arguments: channel_mention, message
        '''
        addCommand()
        msg = ctx.message
        if not msg.channel_mentions:
            channel = msg.channel
        else:
            channel = msg.channel_mentions[0]
        txt = msg.content
        txt = txt.replace(ctx.prefix + "say", "", 1)
        txt = txt.replace(channel.mention, "", 1)
        txt = txt.strip()
        if not txt:
            raise commands.CommandError(message=f'Required argument missing: `message`.')
        try:
            await msg.delete()
        except discord.Forbidden:
            ctx.send(f'Missing permissions: `delete_message`.')

        await channel.send(txt)
    
    @commands.command(name='embed')
    @is_admin()
    async def _embed(self, ctx, title='Announcement', channel='', *message):
        '''
        Sends an embed. (Admin+)
        Arguments: title, channel (optional), message
        '''
        addCommand()

        c = ctx.channel
        if any(chan.mention == channel for chan in ctx.guild.text_channels):
            c = ctx.message.channel_mentions[0]
            msg = ' '.join(message)
        else:
            msg = channel + ' ' + ' '.join(message)
        
        if not msg:
            raise commands.CommandError(message=f'Required argument missing: `message`.')
        
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            ctx.send(f'Missing permissions: `delete_message`.')

        embed = discord.Embed(title=title, colour=0x00b2ff, timestamp=datetime.utcnow(), description=msg)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)

        await c.send(embed=embed)
        

    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    async def eval(self, ctx, *, body=''):
        '''
        Evaluates code
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        env = {
            'bot': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            '_': self._last_result
        }

        env.update(globals())

        body = str(body).strip()
        if not body:
            raise commands.CommandError(message=f'Required argument missing: `body`.')

        body = self.cleanup_code(body)
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            raise commands.CommandError(message=f'Error:\n```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
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
                self._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')

    @commands.command(hidden=True)
    @is_owner()
    async def load(self, ctx, *, module):
        """Loads a module."""
        addCommand()
        try:
            self.bot.load_extension(f'cogs.{module}')
        except:
            raise commands.CommandError(message=f'Error:\n```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(f'Loaded extension: **{module}**')

    @commands.command(hidden=True)
    @is_owner()
    async def unload(self, ctx, *, module):
        """Unloads a module."""
        addCommand()
        try:
            self.bot.unload_extension(f'cogs.{module}')
        except:
            raise commands.CommandError(message=f'Error:\n```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(f'Unloaded extension: **{module}**')

    @commands.command(hidden=True)
    @is_owner()
    async def reload(self, ctx, *, module):
        """Reloads a module."""
        addCommand()
        try:
            self.bot.reload_extension(f'cogs.{module}')
        except:
            raise commands.CommandError(message=f'Error:\n```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(f'Reloaded extension: **{module}**')

    @commands.command(hidden=True)
    @portables_admin()
    @portables_only()
    async def reload_sheets(self, ctx):
        '''
        Reloads the sheets extension.
        '''
        try:
            self.bot.reload_extension(f'cogs.sheets')
        except:
            raise commands.CommandError(message=f'Error:\n```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.send(f'Reloaded extension: **sheets**')

    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    async def repl(self, ctx):
        """Launches an interactive REPL session."""
        addCommand()

        variables = {
            'ctx': ctx,
            'bot': self.bot,
            'message': ctx.message,
            'guild': ctx.guild,
            'channel': ctx.channel,
            'author': ctx.author,
            '_': None,
        }

        if ctx.channel.id in self.sessions:
            raise commands.CommandError(message=f'Error: duplicate REPL session in `{ctx.channel.name}`.')

        self.sessions.add(ctx.channel.id)
        await ctx.send('Enter code to execute or evaluate. `exit()` or `quit` to exit.')

        def check(m):
            return m.author.id == ctx.author.id and \
                   m.channel.id == ctx.channel.id and \
                   m.content.startswith('`')

        while True:
            try:
                response = await self.bot.wait_for('message', check=check, timeout=10.0 * 60.0)
            except asyncio.TimeoutError:
                await ctx.send('Exiting REPL session.')
                self.sessions.remove(ctx.channel.id)
                break

            cleaned = self.cleanup_code(response.content)

            if cleaned in ('quit', 'exit', 'exit()'):
                await ctx.send('Exiting.')
                self.sessions.remove(ctx.channel.id)
                return

            executor = exec
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
                    await ctx.send(self.get_syntax_error(e))
                    continue

            variables['message'] = response

            fmt = None
            stdout = io.StringIO()

            try:
                with redirect_stdout(stdout):
                    result = executor(code, variables)
                    if inspect.isawaitable(result):
                        result = await result
            except Exception as e:
                value = stdout.getvalue()
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
    async def uptime(self, ctx):
        '''
        Uptime statistics
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        events = await Uptime.query.order_by(Uptime.time.asc()).gino.all()

        now = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        uptime_today = uptime_fraction(events, now.year, now.month, now.day)
        uptime_today_round = '{:.1f}'.format(uptime_today*100)

        uptime_month = uptime_fraction(events, now.year, now.month)
        uptime_month_round = '{:.1f}'.format(uptime_month*100)

        loc = mdates.WeekdayLocator()

        formatter = DateFormatter('%d %b')

        plt.style.use('dark_background')

        fig, ax = plt.subplots()

        times = []
        uptimes = []
        for i in range(30):
            day = now - timedelta(days=i)
            times.append(day)
            uptimes.append(100 * uptime_fraction(events, day.year, day.month, day.day))

        dates = date2num(times)
        plt.plot_date(dates, uptimes, color='#47a0ff', linestyle='-', ydate=False, xdate=True)

        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(formatter)

        ax.yaxis.grid()

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)

        plt.savefig('images/uptime.png', transparent=True)
        plt.close(fig)

        with open('images/uptime.png', 'rb') as f:
            file = io.BytesIO(f.read())
        
        txt = f'Today: `{uptime_today_round}%`\nMonthly: `{uptime_month_round}%`'
        
        embed = discord.Embed(title='Uptime', colour=0x00b2ff, timestamp=datetime.utcnow(), description=txt)
        
        image = discord.File(file, filename='uptime.png')
        embed.set_image(url=f'attachment://uptime.png')

        await ctx.send(file=image, embed=embed)

    @commands.command()
    async def invite(self, ctx):
        '''
        Get an invite link to invite RuneClock to your servers.
        '''
        url = 'https://discordapp.com/api/oauth2/authorize?client_id=449462150491275274&permissions=469879878&scope=bot'
        await ctx.send(f'**RuneClock invite link:**\n{url}')
    
    @commands.command(hidden=True, aliases=['gino'])
    async def ginonotes(self, ctx):
        '''
        Get link to gino notes.
        '''
        url = 'https://github.com/makupi/gino-notes/wiki'
        await ctx.send(f'**GINO notes:**\n{url}')
    
    @commands.command(hidden=True)
    @is_owner()
    async def add_item_osrs(self, ctx, id=0):
        '''
        Add an item to the OSRS item database by ID.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not is_int(id):
            raise commands.CommandError(message=f'Required argument missing: `ID`.')
        id = int(id)
        item = await OSRSItem.get(id)

        data_url = f'http://services.runescape.com/m=itemdb_oldschool/api/catalogue/detail.json?item={id}'
        graph_url = f'http://services.runescape.com/m=itemdb_oldschool/api/graph/{id}.json'
        item_data = None
        graph_data = None

        while not item_data and not graph_data:
            if not item_data:
                r = await self.bot.aiohttp.get(data_url)
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
        
        name = item_data['item']['name']
        icon_url = item_data['item']['icon_large']
        type = item_data['item']['type']
        description = item_data['item']['description']
        members = True if item_data['item']['members'] == 'true' else False
        
        prices = []
        for time, price in graph_data['daily'].items():
            prices.append(price)
        
        current = prices[len(prices) - 1]
        yesterday = prices[len(prices) - 2]
        month_ago = prices[len(prices) - 31]
        three_months_ago = prices[len(prices) - 91]
        half_year_ago = prices[0]

        today = str(int(current) - int(yesterday))
        day30 = '{:.1f}'.format((int(current) - int(month_ago)) / int(month_ago) * 100) + '%'
        day90 = '{:.1f}'.format((int(current) - int(three_months_ago)) / int(three_months_ago) * 100) + '%'
        day180 = '{:.1f}'.format((int(current) - int(half_year_ago)) / int(half_year_ago) * 100) + '%'

        if not item:
            await OSRSItem.create(id=int(id), name=name, icon_url=icon_url, type=type, description=description, members=members, current=str(current), today=str(today), day30=day30, day90=day90, day180=day180, graph_data=graph_data)
        else:
            await item.update(current=str(current), today=str(today), day30=day30, day90=day90, day180=day180, graph_data=graph_data).apply()

        await ctx.send(f'Item added: `{name}`: `{current}`.')
    
    @commands.command(hidden=True)
    @is_owner()
    async def remove_item_osrs(self, ctx, id=0):
        '''
        Remove an item from the OSRS item database by ID.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not is_int(id):
            raise commands.CommandError(message=f'Required argument missing: `ID`.')
        id = int(id)
        item = await OSRSItem.get(id)

        if not item:
            raise commands.CommandError(message=f'Could not find item by id: `{id}`.')
        
        await item.delete()

        await ctx.send(f'Item removed: `{id}`: `{item.name}`.')

    @commands.command(hidden=True)
    @is_owner()
    async def add_item_rs3(self, ctx, id=0):
        '''
        Add an item to the RS3 item database by ID.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not is_int(id):
            raise commands.CommandError(message=f'Required argument missing: `ID`.')
        id = int(id)
        item = await RS3Item.get(id)

        data_url = f'http://services.runescape.com/m=itemdb_rs/api/catalogue/detail.json?item={id}'
        graph_url = f'http://services.runescape.com/m=itemdb_rs/api/graph/{id}.json'
        item_data = None
        graph_data = None

        while not item_data and not graph_data:
            if not item_data:
                r = await self.bot.aiohttp.get(data_url)
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
        
        name = item_data['item']['name']
        icon_url = item_data['item']['icon_large']
        type = item_data['item']['type']
        description = item_data['item']['description']
        members = True if item_data['item']['members'] == 'true' else False
        
        prices = []
        for time, price in graph_data['daily'].items():
            prices.append(price)
        
        current = prices[len(prices) - 1]
        yesterday = prices[len(prices) - 2]
        month_ago = prices[len(prices) - 31]
        three_months_ago = prices[len(prices) - 91]
        half_year_ago = prices[0]

        today = str(int(current) - int(yesterday))
        day30 = '{:.1f}'.format((int(current) - int(month_ago)) / int(month_ago) * 100) + '%'
        day90 = '{:.1f}'.format((int(current) - int(three_months_ago)) / int(three_months_ago) * 100) + '%'
        day180 = '{:.1f}'.format((int(current) - int(half_year_ago)) / int(half_year_ago) * 100) + '%'

        if not item:
            await RS3Item.create(id=int(id), name=name, icon_url=icon_url, type=type, description=description, members=members, current=str(current), today=str(today), day30=day30, day90=day90, day180=day180, graph_data=graph_data)
        else:
            await item.update(current=str(current), today=str(today), day30=day30, day90=day90, day180=day180, graph_data=graph_data).apply()

        await ctx.send(f'Item added: `{name}`: `{current}`.')
    
    @commands.command(hidden=True)
    @is_owner()
    async def remove_item_rs3(self, ctx, id=0):
        '''
        Remove an item from the RS3 item database by ID.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not is_int(id):
            raise commands.CommandError(message=f'Required argument missing: `ID`.')
        id = int(id)
        item = await RS3Item.get(id)

        if not item:
            raise commands.CommandError(message=f'Could not find item by id: `{id}`.')
        
        await item.delete()

        await ctx.send(f'Item removed: `{id}`: `{item.name}`.')
    
    @commands.command(hidden=True)
    @is_owner()
    async def server_top(self, ctx):
        '''
        Return a list of the top-10 servers by size.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)

        msg = '**Top 10 largest servers**'
        for i, guild in enumerate(guilds):
            msg += f'\n{guild.name}: `{guild.member_count}`'
            if i >= 9:
                break
        
        await ctx.send(msg)
    
    @commands.command(hidden=True)
    @is_owner()
    async def sim(self, ctx, key, val, command, *args):
        '''
        Debugging command to simulate a command being invoked from a different context.
        '''
        addCommand()

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
        cmd = self.bot.get_command(command)
        if not cmd:
            raise commands.CommandError(message=f'Command not found: `{command}`.')

        if key == 'user':
            user = await ctx.guild.fetch_member(val)
            if not user:
                raise commands.CommandError(message=f'User not found: `{val}`.')
            ctx.author = user
            ctx.message.author = user
        elif key == 'channel':
            channel = ctx.guild.get_channel(val)
            if not channel:
                raise commands.CommandError(message=f'Channel not found: `{val}`.')
            ctx.channel = channel
            ctx.message.channel = channel
        
        ctx.message.content = command
        if args:
            ctx.message.content += " " + " ".join(args)
        
        ctx.invoked_with = command

        if await cmd.can_run(ctx):
            num_params = len(cmd.clean_params)
            if num_params >= len(args):
                await cmd.callback(self, ctx, *args)
            elif num_params == 0:
                await cmd.callback(self, ctx)
            else:
                args = args[:num_params]
                await cmd.callback(self, ctx, *args)

def setup(bot):
    bot.add_cog(Management(bot))
