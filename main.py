import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sys
import re
import discord
from discord.ext import commands
import codecs
from oauth2client.service_account import ServiceAccountCredentials
import utils
import string
import copy
import aiohttp
import gspread_asyncio
import feedparser
import traceback
from github import Github
from difflib import SequenceMatcher
from database import User, Guild, Role, Mute, Command, Repository, Notification, OnlineNotification, Poll, NewsPost, Uptime, RS3Item, OSRSItem
from database import setup as database_setup
from database import close_connection as close_database
import io
from peony import PeonyClient
import html

'''
Load config file with necessary information
'''
def config_load():
    with codecs.open('data/config.json', 'r', encoding='utf-8-sig') as doc:
        #  Please make sure encoding is correct, especially after editing the config file
        return json.load(doc)

config = config_load()

twitter_client = PeonyClient(consumer_key=config['consumer_key'],
                             consumer_secret=config['consumer_secret'],
                             access_token=config['access_token_key'],
                             access_token_secret=config['access_token_secret'])

commandsAnswered = 0 # int to track how many commands have been processed since startup

# variable used for VOS notifications
districts = ['Cadarn', 'Amlodd', 'Crwys', 'Ithell', 'Hefin', 'Meilyr', 'Trahaearn', 'Iorwerth']

# variable used for role management
notifRoles = ['Warbands', 'Cache', 'Sinkhole', 'Yews', 'Goebies', 'Merchant', 'Spotlight', 'PinkSkirts']
for d in districts:
    notifRoles.append(d)

'''
Used for plagiarism check for smiley applications
'''
def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

'''
Split a string by a list of separating characters
'''
def split(txt, seps):
    # https://stackoverflow.com/questions/4697006/python-split-string-by-list-of-separators/4697047
    default_sep = seps[0]
    # we skip seps[0] because that's the default seperator
    for sep in seps[1:]:
        txt = txt.replace(sep, default_sep)
    return [i.strip() for i in txt.split(default_sep)]

'''
Increment global commands counter
'''
def addCommand():
    global commandsAnswered
    commandsAnswered += 1

'''
Return value of global commands counter
'''
def getCommandsAnswered():
    return commandsAnswered

async def run():
    '''
    Where the bot gets started. If you wanted to create a database connection pool or other session for the bot to use,
    it's recommended that you create it here and pass it to the bot as a kwarg.
    '''
    config = config_load()
    bot = Bot(description=config['description'])
    try:
        await bot.start(config['token'])
    except KeyboardInterrupt:
        await bot.logout()

async def purge_guild(guild):
    '''
    Purge all data relating to a specific Guild from the database
    '''
    roles = await Role.query.where(Role.guild_id == guild.id).gino.all()
    for i in roles:
        await i.delete()
    mutes = await Mute.query.where(Mute.guild_id == guild.id).gino.all()
    for i in mutes:
        await i.delete()
    commands = await Command.query.where(Command.guild_id == guild.id).gino.all()
    for i in commands:
        await i.delete()
    repos = await Repository.query.where(Repository.guild_id == guild.id).gino.all()
    for i in repos:
        await i.delete()
    notifications = await Notification.query.where(Notification.guild_id == guild.id).gino.all()
    for i in notifications:
        await i.delete()
    online_notifications = await OnlineNotification.query.where(OnlineNotification.guild_id == guild.id).gino.all()
    for i in online_notifications:
        await i.delete()
    polls = await Poll.query.where(Poll.guild_id == guild.id).gino.all()
    for i in polls:
        await i.delete()
    await guild.delete()

class Bot(commands.AutoShardedBot):
    def __init__(self, **kwargs):
        intents = discord.Intents.all()
        super().__init__(
            max_messages = 1000000,
            command_prefix=self.get_prefix_,
            description=kwargs.pop('description'),
            case_insensitive=True,
            intents=intents
        )
        self.start_time = None
        self.app_info = None
        self.bot = self
        self.loop.create_task(self.track_start())
        self.loop.create_task(self.initialize())
        self.aiohttp = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        self.agcm = gspread_asyncio.AsyncioGspreadClientManager(utils.get_gspread_creds)
        self.twitter_client = twitter_client

    async def track_start(self):
        '''
        Waits for the bot to connect to discord and then records the time.
        Can be used to work out uptime.
        '''
        # await self.wait_until_ready()
        self.start_time = datetime.utcnow().replace(microsecond=0)

    async def initialize(self):
        print(f'Initializing...')
        config = config_load()
        await asyncio.sleep(10) # Wait to ensure database is running on boot
        await database_setup()
        await asyncio.sleep(5) # Ensure database is up before we continue
        self.loop.create_task(self.load_all_extensions())
        print(f'Loading Discord...')
        await self.wait_until_ready()
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='@RuneClock help'))
        channel = self.get_channel(config['testChannel'])
        self.app_info = await self.application_info()
        msg = (f'Logged in to Discord as: {self.user.name}\n'
            f'Using discord.py version: {discord.__version__}\n'
            f'Owner: {self.app_info.owner}\n'
            f'Time: {str(self.start_time)} UTC')
        print(msg)
        print('-' * 10)
        logging.critical(msg)

        await Uptime.create(time=self.start_time, status='started')

        self.loop.create_task(self.check_guilds())
        self.loop.create_task(self.role_setup())
        if self.start_time:
            if self.start_time > datetime.utcnow() - timedelta(minutes=5):
                try:
                    if channel:
                        await channel.send(msg)
                except:
                    pass
                self.loop.create_task(self.notify())
                self.loop.create_task(self.custom_notify())
                self.loop.create_task(self.unmute())
                self.loop.create_task(self.rsnews())
                self.loop.create_task(self.check_polls())
                self.loop.create_task(self.git_tracking())
                self.loop.create_task(self.price_tracking_rs3())
                self.loop.create_task(self.price_tracking_osrs())
        else:
            self.loop.create_task(self.notify())
            self.loop.create_task(self.custom_notify())
            self.loop.create_task(self.unmute())
            self.loop.create_task(self.rsnews())
            self.loop.create_task(self.check_polls())
            self.loop.create_task(self.git_tracking())
            self.loop.create_task(self.price_tracking_rs3())
            self.loop.create_task(self.price_tracking_osrs())

    async def get_prefix_(self, bot, message):
        '''
        A coroutine that returns a prefix.
        Looks in database for prefix corresponding to the server the message was sent in
        If none found, return default prefix '-'
        '''
        prefix = '-'
        guild = await Guild.get(message.guild.id)
        if guild:
            if guild.prefix:
                prefix = guild.prefix
        return commands.when_mentioned_or(prefix)(bot, message)

    async def load_all_extensions(self):
        '''
        Attempts to load all .py files in /cogs/ as cog extensions
        '''
        # await self.wait_until_ready()
        config = config_load()
        channel = self.get_channel(config['testChannel'])
        cogs = [x.stem for x in Path('cogs').glob('*.py')]
        msg = ""
        discord_msg = ''
        for extension in cogs:
            try:
                print(f'Loading {extension}...')
                self.load_extension(f'cogs.{extension}')
                print(f'Loaded extension: {extension}')
                msg += f'Loaded extension: {extension}\n'
            except commands.ExtensionAlreadyLoaded:
                pass
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
                traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2, file=sys.stdout)
                error = f'{extension}\n {type(e).__name__} : {e}'
                print(f'Failed to load extension: {error}')
                msg += f'Failed to load extension: {error}\n'
                discord_msg += f'Failed to load extension: {error}\n'
        print('-' * 10)
        logging.critical(msg)
        try:
            if 'Failed' in msg:
                await channel.send(discord_msg)
        except discord.Forbidden:
            return

    async def on_ready(self):
        '''
        This event is called every time the bot connects or resumes connection.
        '''
        print('Ready: all guilds loaded.')

    async def check_guilds(self):
        '''
        Function that is run on startup by on_ready
        Checks database for entries of guilds that the bot is no longer a member of
        Adds default prefix entry to prefixes table if guild doesn't have a prefix set
        '''
        logging.info('Checking guilds...')
        print(f'Checking guilds...')
        config = config_load()

        # Adds 100 old messages to cache for each channel in Portables
        for guild in self.guilds:
            if not guild.id == config['portablesServer']:
                continue
            for channel in guild.channels:
                async for message in channel.history(limit=100):
                    self.messages.append(message)

        guilds = await Guild.query.gino.all()
        for guild in guilds:
            in_guild = False
            for guild_2 in self.guilds:
                if guild.id == guild_2.id:
                    in_guild = True
                    break
            if not in_guild:
                await purge_guild(guild)
            elif not guild.prefix:
                await guild.update(prefix='-').apply()

        msg = f'{str(len(self.guilds))} guilds checked and messages cached'
        print(msg)
        print('-' * 10)
        logging.info(msg)


    async def role_setup(self):
        '''
        Sets up message and reactions for role management
        Assumes that no other messages are sent in the role management channels
        Adds messages to cache to track reactions
        '''
        print(f'Initializing role management...')
        logging.info('Initializing role management...')
        config = config_load()

        channels = []
        guilds = await Guild.query.gino.all()
        if guilds:
            for guild in guilds:
                g = self.get_guild(guild.id)
                if guild:
                    if guild.role_channel_id:
                        channel = g.get_channel(guild.role_channel_id)
                        if channel:
                            channels.append(channel)

        if not channels:
            logChannel = self.get_channel(config['testChannel'])
            msg = f'Sorry, I was unable to retrieve any role management channels. Role management is down.'
            print(msg)
            print('-' * 10)
            logging.critical(msg)
            try:
                await logChannel.send(f'Sorry, I was unable to retrieve any role management channels. Role management is down.')
                return
            except discord.Forbidden:
                return
        msg = "React to this message with any of the following emoji to be added to the corresponding role for notifications:\n\n"
        notifEmojis = []
        for r in notifRoles:
            emojiID = config[f'{r.lower()}EmojiID']
            e = self.get_emoji(emojiID)
            notifEmojis.append(e)
            msg += str(e) + ' ' + r + '\n'
        msg += "\nIf you wish to stop receiving notifications, simply remove your reaction. If your reaction isn't there anymore, then you can add a new one and remove it."
        for c in channels:
            try:
                messages = 0
                async for message in c.history(limit=1):
                    messages += 1
                if not messages:
                    await c.send(msg)
                    try:
                        async for message in c.history(limit=1):
                            for e in notifEmojis:
                                await message.add_reaction(e)
                    except Exception as e:
                        print(f'Exception: {e}')
            except discord.Forbidden:
                continue
        msg = f'Role management ready'
        print(msg)
        print('-' * 10)
        logging.info(msg)


    async def on_member_join(self, member):
        '''
        Function to send welcome messages
        '''
        config = config_load()

        #Automatically ban players with problematic names, and do not send welcome messages
        if str(member.guild.id) == config['portablesServer']:
            if 'DISCORD.GG' in member.name.upper() or 'PORTABLE' in member.name.upper():
                try:
                    await member.ban()
                    return
                except discord.Forbidden:
                    return
        try:
            guild = await Guild.get(member.guild.id)
        except:
            return
        if not guild:
            return
        if not guild.welcome_message:
            return
        welcome_message = guild.welcome_message.replace('[user]', member.mention)
        welcome_message = welcome_message.replace('[server]', member.guild.name)
        if not guild.welcome_channel_id:
            return
        welcome_channel = member.guild.get_channel(guild.welcome_channel_id)
        
        try:
            await welcome_channel.send(welcome_message)
        except discord.Forbidden:
            return

    async def on_raw_reaction_add(self, payload):
        '''
        Function to add roles on reactions
        '''
        channel = self.get_channel(payload.channel_id)

        if not channel:
            return

        user = await channel.guild.fetch_member(payload.user_id)

        if not user:
            return

        if user.bot:
            return

        role = None
        try:
            guild = await Guild.get(channel.guild.id)
        except:
            return
        if not guild:
            return

        if guild.role_channel_id == channel.id:
            emoji = payload.emoji
            roleName = emoji.name
            if emoji.name in notifRoles:
                role = discord.utils.get(channel.guild.roles, name=roleName)
            elif guild.id == config['portablesServer'] and emoji.name in ['Fletcher', 'Crafter', 'Brazier', 'Sawmill', 'Range', 'Well', 'Workbench']:
                role = discord.utils.get(channel.guild.roles, name=roleName)
                
            if role:
                try:
                    await user.add_roles(role)
                except discord.Forbidden:
                    pass
        
        if guild.hall_of_fame_channel_id:
            hof_channel = self.get_channel(guild.hall_of_fame_channel_id)
            if hof_channel:
                if str(payload.emoji) == '🌟':
                    message = await channel.fetch_message(payload.message_id)
                    if message:
                        if not message.author.bot and (message.content or message.attachments):
                            for r in message.reactions:
                                if r.emoji == '🌟':
                                    if r.count >= guild.hall_of_fame_react_num:
                                        found = False
                                        hof_msg = None
                                        hof_embed = None
                                        async for msg in hof_channel.history(limit=1000, after=message.created_at):
                                            if msg.embeds:
                                                for embed in msg.embeds:
                                                    footer = embed.footer.text
                                                    if str(message.id) in footer:
                                                        found = True
                                                        hof_msg = msg
                                                        hof_embed = embed
                                                        break
                                        if not found:
                                            embed = discord.Embed(title=f'Hall of fame 🌟 {r.count}', description=message.content, colour=0xffd700, url=message.jump_url, timestamp=message.created_at)
                                            embed.set_author(name=message.author.display_name, icon_url=message.author.avatar_url)
                                            if message.attachments:
                                                for a in message.attachments:
                                                    if 'image' in a.content_type:
                                                        embed.set_image(url=a.url)
                                                        break
                                            embed.set_footer(text=f'Message ID: {message.id}')
                                            await hof_channel.send(embed=embed)
                                        else:
                                            hof_embed.title = f'Hall of fame 🌟 {r.count}'
                                            await hof_msg.edit(embed=hof_embed)
                                    break


    async def on_raw_reaction_remove(self, payload):
        '''
        Function to remove roles on reactions
        '''
        channel = self.get_channel(payload.channel_id)

        if not channel:
            return

        user = await channel.guild.fetch_member(payload.user_id)

        if not user:
            return

        if user.bot:
            return

        role = None
        try:
            guild = await Guild.get(channel.guild.id)
        except:
            return
        if not guild:
            return
        if not guild.role_channel_id == channel.id:
            return

        emoji = payload.emoji
        roleName = emoji.name
        if emoji.name in notifRoles:
            role = discord.utils.get(channel.guild.roles, name=roleName)
        elif guild.id == config['portablesServer'] and emoji.name in ['Fletcher', 'Crafter', 'Brazier', 'Sawmill', 'Range', 'Well', 'Workbench']:
            role = discord.utils.get(channel.guild.roles, name=roleName)

        if role:
            try:
                await user.remove_roles(role)
            except discord.Forbidden:
                return

    async def on_message(self, message):
        '''
        This event triggers on every message received by the bot. Including ones that it sent itself.
        Processes commands
        Also checks if message was a command, and logs processing time
        Tracks message counts for Portables ranks
        Checks Portables applications for plagiarism
        '''
        config = config_load()

        if message.author.bot:
            return  # ignore all bots

        if isinstance(message.channel, discord.abc.PrivateChannel):
            try:
                await message.channel.send(f'Sorry, I don\'t support DMs. If you have any questions, please join the support server: {config["support_server"]}.')
                return
            except:
                return
        try:
            guild = await Guild.get(message.guild.id)
        except:
            return
        if not guild:
            guild = await Guild.create(id=message.guild.id, prefix='-')

        if not message.author.id == message.guild.me.id:
            if guild.delete_channel_ids:
                if message.channel.id in guild.delete_channel_ids:
                    await message.delete()

        now = datetime.utcnow()
        msg = message.content
        prefix = '-'
        if guild.prefix:
            prefix = guild.prefix
        disabled_commands = guild.disabled_commands

        if disabled_commands:
            for command_name in guild.disabled_commands:
                if msg.startswith(f'{prefix}{command_name}') or msg.startswith(f'{self.user.mention} {command_name}'):
                    try:
                        await message.channel.send(f'Sorry, the command **{command_name}** has been disabled in this server. Please contact a server admin to enable it.')
                        return
                    except discord.Forbidden:
                        return

        '''
        In portables server, respond to "!portables"
        '''
        if message.guild.id == config['portablesServer'] and not '!' == prefix:
            if message.content.upper().startswith('!PORTABLE'):
                locChannel = self.bot.get_channel(config['locChannel'])
                if message.channel != locChannel:
                    await message.channel.send(f'Please use this command in {locChannel.mention}.')
                else:
                    portables_command = self.get_command('portables')
                    context = await self.get_context(message=message)
                    await portables_command.callback(self, context)

        if msg.startswith(prefix):
            txt = f'{datetime.utcnow()}: Command \"{msg}\" received; processing...'
            logging.info(str(filter(lambda x: x in string.printable, txt)))
            print(txt)

        await self.process_commands(message)

        if msg.startswith(prefix):
            time = (datetime.utcnow() - now).total_seconds() * 1000
            txt = f'Command \"{msg}\" processed in {time} ms.'
            logging.info(str(filter(lambda x: x in string.printable, txt)))
            print(txt)

        # Message count for portables ranks
        if message.guild.id == config['portablesServer']:
            rank_role = message.guild.get_role(config['rankRole'])
            admin_role = message.guild.get_role(config['adminRole'])
            if rank_role in message.author.roles and not admin_role in message.author.roles:
                name = utils.get_user_name(message.author) # get clean name
                agc = await self.agcm.authorize()
                ss = await agc.open(config['adminSheetName'])
                admin_sheet = await ss.worksheet('Rank Reports')
                header_rows = 4
                discord_col = 66

                ranks = await admin_sheet.col_values(1)
                ranks = ranks[header_rows:]
                monthly_message_counts = await admin_sheet.col_values(discord_col)
                monthly_message_counts = monthly_message_counts[header_rows:]
                total_message_counts = await admin_sheet.col_values(discord_col+1)
                total_message_counts = total_message_counts[header_rows:]

                for i, rank in enumerate(ranks):
                    if not rank:
                        ranks = ranks[:i]
                        monthly_message_counts = monthly_message_counts[:i]
                        total_message_counts = total_message_counts[:i]
                        break

                row = 0
                index = 0
                for i, rank in enumerate(ranks):
                    if name.upper() == rank.upper():
                        row = i + 1 + header_rows
                        index = i
                        break
                if not row:
                    for i, rank in enumerate(ranks):
                        if name.upper() in rank.upper():
                            row = i + 1 + header_rows
                            index = i
                            break
                if row:
                    try:
                        monthly = monthly_message_counts[index].strip()
                    except:
                        monthly = '0'
                    try:
                        total = total_message_counts[index].strip()
                    except:
                        total = '0'
                    if not monthly:
                        monthly = '0'
                    if not total:
                        total = '0'
                    if utils.is_int(monthly) and utils.is_int(total):
                        monthly, total = int(monthly), int(total)
                        monthly += 1
                        total += 1
                        await admin_sheet.update_cell(row, discord_col, str(monthly))
                        await admin_sheet.update_cell(row, discord_col+1, str(total))
            # Plagiarism check for Portables smiley applications
            if message.channel.id == config['applicationChannel']:
                if not rank_role in message.author.roles:
                    application_lines = ["0. What is your RSN?".upper(),
                                            "1. Have you fully read our #rules?".upper(),
                                            "2. Do you acknowledge and agree to the smiley terms?".upper(),
                                            "3. What is expected from smiley ranks?".upper(),
                                            "4. If you are genuinely applying to help the FC as a smiley, in what ways do you wish to help?".upper(),
                                            "5. Do you have any goals you wish to achieve with portables and the FC?".upper(),
                                            "6. Would you be interested in or intend to become an official rank in the future?".upper()]
                    
                    old_messages = await message.channel.history(limit=100).flatten()
                    for old_msg in old_messages:
                        if old_msg.id == message.id or old_msg.author.bot or not message.clean_content.upper().startswith(application_lines[0]) or rank_role in message.author.roles:
                            old_messages.remove(old_msg)

                    txt = message.clean_content.upper().replace('*', '').replace('`', '').replace('_', '')

                    # Check if this message is an application
                    if not txt.startswith(application_lines[0]):
                        return

                    answers = split(txt, application_lines)
                    clean_answers = []

                    for answer in answers:
                        if answer:
                            clean_answers.append(answer)

                    if len(clean_answers) != 7:
                        await message.channel.send('Formatting error. Please copy the application template from the pinned messages in this channel and try again. Ensure that you answer all questions.')
                        return
                    
                    for answer in clean_answers:
                        if not answer:
                            await message.channel.send('Application incomplete. Please ensure that you have answered all questions.')
                            return
                    
                    answers_str = ';'.join(clean_answers)

                    msg = ''
                    
                    for old_msg in old_messages:
                        old_answers = split(old_msg.clean_content.upper().replace('*', '').replace('`', '').replace('_', ''), application_lines)
                        clean_old_answers = []
                        for a in old_answers:
                            if a:
                                clean_old_answers.append(a)
                        if len(clean_old_answers) == 7:
                            old_answers_str = ';'.join(clean_old_answers)
                            sim = similarity(answers_str, old_answers_str)
                            if sim > 0.75:
                                new_str = f'`{int(sim*100)}%` similarity to application from `{old_msg.author.display_name}` on `{old_msg.created_at.strftime("%Y-%m-%d")}`\n'
                                if len(msg) + len(new_str) < 1900:
                                    msg += new_str
                                else:
                                    break
                    
                    if msg:
                        msg = '**Possible plagiarism detected**\n' + msg
                        await message.add_reaction('🚫')
                        await message.channel.send(msg)
                    else:
                        await message.add_reaction('✅')

                    

    async def notify(self):
        '''
        Function to send D&D notifications
        Runs every 10 s.
        Merchant and spotlight are exceptions, run every 5 min and 1 min, respectively.
        At first run, reads sent notifications to avoid duplicates on restart.
        '''
        print(f'Initializing notifications...')
        logging.info('Initializing notifications...')
        config = config_load()
        channel = self.get_channel(config['testNotificationChannel'])
        
        if not channel:
            logChannel = self.get_channel(config['testChannel'])
            msg = f'Sorry, I was unable to retrieve any notification channels. Notifications are down.'
            print(msg)
            logging.critical(msg)
            try:
                await logChannel.send(msg)
                return
            except discord.Forbidden:
                return
        notifiedThisHourWarbands = False
        notifiedThisHourVOS = False
        notifiedThisHourCache = False
        notifiedThisHourYews48 = False
        notifiedThisHourYews140 = False
        notifiedThisHourGoebies = False
        notifiedThisHourSinkhole = False
        notifiedThisHourPinkSkirts = False
        notifiedThisDayMerchant = False
        notifiedThisDaySpotlight = False
        reset = False
        currentTime = datetime.utcnow()
        async for m in channel.history(limit=100):
            if m.created_at.day == currentTime.day:
                if 'Merchant' in m.content:
                    notifiedThisDayMerchant = True
                    continue
                if 'spotlight' in m.content:
                    notifiedThisDaySpotlight = True
                    continue
                if m.created_at.hour == currentTime.hour:
                    if 'Warbands' in m.content:
                        notifiedThisHourWarbands = True
                        continue
                    if any(d in m.content for d in districts):
                        if currentTime.minute <= 1:
                            reset = True
                        notifiedThisHourVOS = True
                        continue
                    if 'Cache' in m.content:
                        notifiedThisHourCache = True
                        continue
                    if 'yew' in m.content:
                        if '48' in m.content:
                            notifiedThisHourYews48 = True
                        elif '140' in m.content:
                            notifiedThisHourYews140 = True
                        continue
                    if 'Goebies' in m.content:
                        notifiedThisHourGoebies = True
                        continue
                    if 'Sinkhole' in m.content:
                        notifiedThisHourSinkhole = True
                        continue
                    if 'Pink' in m.content and 'Skirt' in m.content:
                        notifiedThisHourPinkSkirts = True
                        continue
            else:
                break
        await asyncio.sleep(3) # Ensure values are initialized from dndCommands.py
        msg = f'Notifications ready'
        logging.info(msg)
        print(msg)
        print('-' * 10)
        i = 0
        while True:
            try:
                now = datetime.utcnow()
                if not notifiedThisDayMerchant and now.hour <= 2:
                    if self.bot.next_merchant > now + timedelta(hours=1):
                        txt = self.bot.merchant

                        channels = []
                        guilds = await Guild.query.gino.all()
                        for guild in guilds:
                            if guild.notification_channel_id:
                                c = self.get_channel(guild.notification_channel_id)
                                if c:
                                    channels.append(c)

                        for c in channels:
                            role = ''
                            for r in c.guild.roles:
                                if 'MERCHANT' in r.name.upper():
                                    role = r
                                    break
                            if role:
                                role = role.mention
                            try:
                                await c.send(f'{role}\n**Traveling Merchant** stock {now.strftime("%d %b")}\n{txt}')
                            except discord.Forbidden:
                                pass
                        notifiedThisDayMerchant = True

                if not notifiedThisDaySpotlight and now.hour <= 1:
                    if self.bot.next_spotlight > now + timedelta(days=2, hours=1):
                        minigame = self.bot.spotlight
                        emoji = config['spotlightEmoji']

                        channels = []
                        guilds = await Guild.query.gino.all()
                        for guild in guilds:
                            if guild.notification_channel_id:
                                c = self.get_channel(guild.notification_channel_id)
                                if c:
                                    channels.append(c)

                        for c in channels:
                            role = ''
                            for r in c.guild.roles:
                                if 'SPOTLIGHT' in r.name.upper():
                                    role = r
                                    break
                            if role:
                                role = role.mention
                            msg = f'{emoji} **{minigame}** is now the spotlighted minigame. {role}'
                            try:
                                await c.send(msg)
                            except discord.Forbidden:
                                continue
                        notifiedThisDaySpotlight = True
                if not notifiedThisHourVOS and now.minute <= 1:
                    if self.bot.next_vos > now + timedelta(minutes=1):
                        channels = []
                        guilds = await Guild.query.gino.all()
                        for guild in guilds:
                            if guild.notification_channel_id:
                                c = self.get_channel(guild.notification_channel_id)
                                if c:
                                    channels.append(c)
                        
                        for c in channels:
                            msg = ''
                            for d in self.vos['vos']:
                                msgName = f'msg{d}'
                                role = ''
                                for r in c.guild.roles:
                                    if d.upper() in r.name.upper():
                                        role = r
                                        break
                                if role:
                                    role = role.mention
                                msg += config[msgName] + role + '\n'
                            if msg:
                                notifiedThisHourVOS = True
                                try:
                                    await c.send(msg)
                                except discord.Forbidden:
                                    continue
                if not notifiedThisHourWarbands and now.minute >= 45 and now.minute <= 46:
                    if self.bot.next_warband - now <= timedelta(minutes=15):
                        channels = []
                        guilds = await Guild.query.gino.all()
                        for guild in guilds:
                            if guild.notification_channel_id:
                                c = self.get_channel(guild.notification_channel_id)
                                if c:
                                    channels.append(c)
                        for c in channels:
                            role = ''
                            for r in c.guild.roles:
                                if 'WARBAND' in r.name.upper():
                                    role = r
                                    break
                            if role:
                                role = role.mention
                            try:
                                await c.send(config['msgWarbands'] + role)
                            except discord.Forbidden:
                                continue
                            notifiedThisHourWarbands = True
                            
                if not notifiedThisHourCache and now.minute >= 55 and now.minute <= 56:
                    channels = []
                    guilds = await Guild.query.gino.all()
                    for guild in guilds:
                        if guild.notification_channel_id:
                            c = self.get_channel(guild.notification_channel_id)
                            if c:
                                channels.append(c)
                    
                    for c in channels:
                        role = ''
                        for r in c.guild.roles:
                            if 'CACHE' in r.name.upper():
                                role = r
                                break
                        if role:
                            role = role.mention
                        try:
                            await c.send(config['msgCache'] + role)
                        except discord.Forbidden:
                            continue
                    notifiedThisHourCache = True
                if not notifiedThisHourYews48 and now.hour == 23 and now.minute >= 45 and now.minute <= 46:
                    channels = []
                    guilds = await Guild.query.gino.all()
                    for guild in guilds:
                        if guild.notification_channel_id:
                            c = self.get_channel(guild.notification_channel_id)
                            if c:
                                channels.append(c)

                    for c in channels:
                        role = ''
                        for r in c.guild.roles:
                            if 'YEW' in r.name.upper():
                                role = r
                                break
                        if role:
                            role = role.mention
                        try:
                            await c.send(config['msgYews48'] + role)
                        except discord.Forbidden:
                            continue
                    notifiedThisHourYews48 = True
                if not notifiedThisHourYews140 and now.hour == 16 and now.minute >= 45 and now.minute <= 46:
                    channels = []
                    guilds = await Guild.query.gino.all()
                    for guild in guilds:
                        if guild.notification_channel_id:
                            c = self.get_channel(guild.notification_channel_id)
                            if c:
                                channels.append(c)

                    for c in channels:
                        role = ''
                        for r in c.guild.roles:
                            if 'YEW' in r.name.upper():
                                role = r
                                break
                        if role:
                            role = role.mention
                        try:
                            await c.send(config['msgYews140'] + role)
                        except discord.Forbidden:
                            continue
                    notifiedThisHourYews140 = True
                if not notifiedThisHourGoebies and now.hour in [11, 23] and now.minute >= 45 and now.minute <= 46:
                    channels = []
                    guilds = await Guild.query.gino.all()
                    for guild in guilds:
                        if guild.notification_channel_id:
                            c = self.get_channel(guild.notification_channel_id)
                            if c:
                                channels.append(c)

                    for c in channels:
                        role = ''
                        for r in c.guild.roles:
                            if 'GOEBIE' in r.name.upper():
                                role = r
                                break
                        if role:
                            role = role.mention
                        try:
                            await c.send(config['msgGoebies'] + role)
                        except discord.Forbidden:
                            continue
                    notifiedThisHourGoebies = True
                if not notifiedThisHourSinkhole and now.minute >= 25 and now.minute <= 26:
                    channels = []
                    guilds = await Guild.query.gino.all()
                    for guild in guilds:
                        if guild.notification_channel_id:
                            c = self.get_channel(guild.notification_channel_id)
                            if c:
                                channels.append(c)

                    for c in channels:
                        role = ''
                        for r in c.guild.roles:
                            if 'SINKHOLE' in r.name.upper():
                                role = r
                                break
                        if role:
                            role = role.mention
                        try:
                            await c.send(config['msgSinkhole'] + role)
                        except discord.Forbidden:
                            continue
                    notifiedThisHourSinkhole = True
                
                # Notify of Pink Skirts events
                if not notifiedThisHourPinkSkirts and i == 0:
                    request = self.bot.twitter_client.api.statuses.user_timeline.get(screen_name='PinkSkirtsRS', count=10)
                    responses = request.iterator.with_max_id()

                    ps_tweets = []
                    async for tweets in responses:
                        ps_tweets += [tweet for tweet in tweets]

                        if len(ps_tweets) > 10:
                            break
                    
                    ps_tweets = sorted(ps_tweets, key=lambda t: datetime.strptime(t['created_at'], '%a %b %d %H:%M:%S %z %Y'), reverse=True)

                    for tweet in ps_tweets:
                        tweet_time = datetime.strptime(tweet['created_at'], '%a %b %d %H:%M:%S %z %Y').replace(tzinfo=None)
                        time_diff = now - tweet_time if now > tweet_time else tweet_time - now
                        if time_diff > timedelta(minutes=2):
                            break
                        msg = tweet['text']
                        if msg.startswith('RT'):
                            break
                        msg = html.unescape(msg)

                        channels = []
                        guilds = await Guild.query.gino.all()
                        for guild in guilds:
                            if guild.notification_channel_id:
                                c = self.get_channel(guild.notification_channel_id)
                                if c:
                                    channels.append(c)
                        for c in channels:
                            role = ''
                            for r in c.guild.roles:
                                if 'PINK' in r.name.upper() and 'SKIRT' in r.name.upper():
                                    role = r
                                    break
                            if role:
                                role = role.mention
                            else:
                                role = 'Pink Skirts'
                            
                            c_msg = f'{config["pinkskirtsEmoji"]} **Pink Skirts** event:\n{msg} {role}'

                            try:
                                await c.send(c_msg)
                            except discord.Forbidden:
                                continue

                        notifiedThisHourPinkSkirts = True
                        break


                if now.minute > 1 and reset:
                    reset = False
                if now.minute == 0 and not reset:
                    notifiedThisHourWarbands = False
                    notifiedThisHourVOS = False
                    notifiedThisHourCache = False
                    notifiedThisHourYews48 = False
                    notifiedThisHourYews140 = False
                    notifiedThisHourGoebies = False
                    notifiedThisHourSinkhole = False
                    notifiedThisHourPinkSkirts = False
                    if now.hour == 0:
                        notifiedThisDayMerchant = False
                        notifiedThisDaySpotlight = False
                    reset = True
                await asyncio.sleep(15)
                i = (i + 1) % 4
            except Exception as e:
                error = f'Encountered the following error in notification loop:\n{type(e).__name__}: {e}'
                logging.critical(error)
                print(error)
                try:
                    await logChannel.send(error)
                except:
                    pass
                await asyncio.sleep(5)

    async def custom_notify(self):
        '''
        Function to send custom notifications
        '''
        logging.info('Initializing custom notifications...')
        while True:
            to_notify = []
            deleted = []
            notifications = await Notification.query.gino.all()
            if notifications:
                for notification in notifications:
                    guild = self.get_guild(notification.guild_id)
                    if not guild:
                        continue
                    channel = guild.get_channel(notification.channel_id)
                    if not channel:
                        continue
                    time = notification.time
                    interval = timedelta(seconds = notification.interval)
                    if time > datetime.utcnow():
                        continue
                    to_notify.append([channel, notification.message])
                    if interval.total_seconds() != 0:
                        while time < datetime.utcnow():
                            time += interval
                        await notification.update(time=time).apply()
                    else:
                        deleted.append(notification.guild_id)
                        await notification.delete()

                for x in to_notify:
                    channel, message = x
                    try:
                        await channel.send(message)
                    except discord.Forbidden:
                        pass
                
                if deleted:
                    for guild_id in deleted:
                        notifications = await Notification.query.where(Notification.guild_id==guild_id).order_by(Notification.notification_id.asc()).gino.all()
                        if notifications:
                            for i, notification in enumerate(notifications):
                                await notification.update(notification_id=i).apply()
            await asyncio.sleep(30)

    async def unmute(self):
        '''
        Function to unmute members when mutes expire
        '''
        logging.info('Initializing unmute...')
        while True:
            to_unmute = []
            mutes = await Mute.query.gino.all()
            if mutes:
                for mute in mutes:
                    guild = self.get_guild(mute.guild_id)
                    if not guild:
                        continue
                    member = await guild.fetch_member(mute.member_id)
                    if not member:
                        await mute.delete()
                        continue
                    expires = mute.expiration
                    if expires < datetime.utcnow():
                        await mute.delete()
                        mute_role = discord.utils.find(lambda r: 'MUTE' in r.name.upper(), guild.roles)
                        if mute_role:
                            if mute_role in member.roles:
                                to_unmute.append([member, mute_role, guild])
                for x in to_unmute:
                    member, mute_role, guild = x
                    try:
                        await member.remove_roles(mute_role, reason='Temp mute expired.')

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
                                        pass
                    except discord.Forbidden:
                        continue
            await asyncio.sleep(60)

    async def send_news(self, post, osrs):
        '''
        Function to send a message for a runescape newspost
        '''
        embed = discord.Embed(title=f'**{post.title}**', description=post.description, url=post.link, timestamp=datetime.utcnow())
        if osrs:
            embed.set_author(name='Old School RuneScape News', url='http://services.runescape.com/m=news/archive?oldschool=1', icon_url='https://i.imgur.com/2d5RrGi.png')
        else:
            embed.set_author(name='RuneScape News', url='http://services.runescape.com/m=news/list', icon_url='https://i.imgur.com/OiV3xHn.png')
        if post.category:
            embed.set_footer(text=post.category)
        
        if post.image_url:
            embed.set_image(url=post.image_url)

        to_send = []
        guilds = await Guild.query.gino.all()
        for guild in guilds:
            if not osrs:
                if guild.rs3_news_channel_id:
                    news_channel = self.get_channel(guild.rs3_news_channel_id)
                else:
                    continue
            else:
                if guild.osrs_news_channel_id:
                    news_channel = self.get_channel(guild.osrs_news_channel_id)
                else:
                    continue
            if news_channel:
                to_send.append(news_channel)
        for news_channel in to_send:
            try:
                await news_channel.send(embed=embed)
            except discord.Forbidden:
                continue

    async def rsnews(self):
        '''
        Function to send messages from Runescape news rss feed.
        '''
        await asyncio.sleep(300)
        logging.info('Initializing rs news...')
        rs3_url = 'http://services.runescape.com/m=news/latest_news.rss'
        osrs_url = 'http://services.runescape.com/m=news/latest_news.rss?oldschool=true'
        while True:
            try:
                r = await self.bot.aiohttp.get(rs3_url)
                async with r:
                    if r.status != 200:
                        await asyncio.sleep(900)
                        continue
                    content = await r.content.read()
                    rs3_data = io.BytesIO(content)

                r = await self.bot.aiohttp.get(osrs_url)
                async with r:
                    if r.status != 200:
                        await asyncio.sleep(900)
                        continue
                    content = await r.content.read()
                    osrs_data = io.BytesIO(content)

                if not rs3_data or not osrs_data:
                    await asyncio.sleep(900)
                    continue

                rs3_feed = feedparser.parse(rs3_data)
                osrs_feed = feedparser.parse(osrs_data)
                
                to_send = []
                news_posts = await NewsPost.query.gino.all()

                for post in reversed(rs3_feed.entries):
                    if not any(post.link == news_post.link for news_post in news_posts):
                        time = datetime.strptime(post.published, '%a, %d %b %Y %H:%M:%S %Z')

                        category = None
                        if post.category:
                            category = post.category

                        image_url = None
                        if post.enclosures:
                            enclosure = post.enclosures[0]
                            if any(txt in enclosure.type for txt in ['image', 'jpeg', 'jpg', 'png']):
                                image_url = enclosure.href

                        news_post = await NewsPost.create(link=post.link, game='rs3', title=post.title, description=post.description, time=time, category=category, image_url=image_url)
                        to_send.append([news_post, False])
            
                for post in reversed(osrs_feed.entries):
                    if not any(post.link == news_post.link for news_post in news_posts):
                        time = datetime.strptime(post.published, '%a, %d %b %Y %H:%M:%S %Z')

                        category = None
                        if post.category:
                            category = post.category

                        image_url = None
                        if post.enclosures:
                            enclosure = post.enclosures[0]
                            if any(txt in enclosure.type for txt in ['image', 'jpeg', 'jpg', 'png']):
                                image_url = enclosure.href

                        news_post = await NewsPost.create(link=post.link, game='osrs', title=post.title, description=post.description, time=time, category=category, image_url=image_url)
                        to_send.append([news_post, True])

                for x in to_send:
                    news_post, osrs = x
                    await self.send_news(news_post, osrs)

                # sleep for 15 min to avoid rate limits causing 404 errors
                await asyncio.sleep(900)
            except Exception as e:
                error = f'Encountered the following error in news loop:\n{type(e).__name__}: {e}'
                logging.critical(error)
                print(error)
                try:
                    config = config_load()
                    logChannel = self.get_channel(config['testChannel'])
                    await logChannel.send(error)
                except:
                    pass
                await asyncio.sleep(900)
    
    async def check_polls(self):
        '''
        Function to check if there are any polls that have to be closed.
        '''
        logging.info('Initializing polls...')
        while True:
            polls = await Poll.query.gino.all()
            now = datetime.utcnow()
            for poll in polls:
                end_time = poll.end_time
                if now > end_time:
                    try:
                        guild = self.get_guild(poll.guild_id)
                        channel = guild.get_channel(poll.channel_id)
                        msg = await channel.fetch_message(poll.message_id)

                        results = {}
                        votes = 0
                        for reaction in msg.reactions:
                            results[str(reaction.emoji)] = reaction.count - 1
                            votes += reaction.count - 1
                        max_score = 0
                        winner = ''
                        tie = False
                        for emoji, score in results.items():
                            if score > max_score:
                                max_score = score
                                winner = emoji
                                tie = False
                            elif score == max_score:
                                tie = True
                                winner += f' and {emoji}'
                        percentage = int((max_score)/max(1,votes)*100)

                        embed = msg.embeds[0]
                        if not tie:
                            embed.add_field(name='Results', value=f'Option {winner} won with {percentage}% of the votes!')
                        else:
                            embed.add_field(name='Results', value=f'It\'s a tie! Options {winner} each have {percentage}% of the votes!')
                        await msg.edit(embed=embed)
                    except:
                        pass
                    await poll.delete()
            await asyncio.sleep(60)

    async def git_tracking(self):
        '''
        Function to check tracked git repositories for new commits.
        '''
        logging.info('Initializing git tracking...')
        config = config_load()
        while True:
            try:
                g = Github(config['github_access_token'])

                repositories = await Repository.query.gino.all()
                for repo in repositories:
                    guild_id = repo.guild_id
                    channel_id = repo.channel_id
                    user_name = repo.user_name
                    repo_name = repo.repo_name
                    sha = repo.sha

                    
                    guild = self.get_guild(guild_id)
                    if not guild:
                        await repo.delete()
                        continue
                    channel = guild.get_channel(channel_id)
                    if not channel:
                        await repo.delete()
                        continue

                    user = g.get_user(user_name)
                    if not user:
                        await repo.delete()
                        continue

                    repos = user.get_repos()
                    if not repos:
                        await repo.delete()
                        continue
                    
                    num_repos = 0
                    for _ in repos:
                        num_repos += 1

                    for i, rep in enumerate(repos):
                        if rep.name.upper() == repo_name.upper():
                            break
                    
                    if i == num_repos - 1 and rep.name.upper() != repo_name.upper():
                        await repo.delete()
                        continue
                    
                    commits = rep.get_commits()

                    new_commits = []

                    for i, commit in enumerate(commits):
                        if commit.sha != sha:
                            new_commits.append(commit)
                        else:
                            break
                    
                    if not new_commits:
                        continue

                    for i, commit in enumerate(reversed(new_commits)):
                        r = await self.bot.aiohttp.get(commit.url)
                        async with r:
                            if r.status != 200:
                                continue
                            data = await r.json()
                        
                        if i == len(new_commits) - 1:
                            await repo.update(sha=commit.sha).apply()
                        
                        embed = discord.Embed(title=f'{user_name}/{repo_name}', colour=discord.Colour.blue(), timestamp=datetime.strptime(data['commit']['author']['date'], "%Y-%m-%dT%H:%M:%SZ"), description=f'[`{commit.sha[:7]}`]({commit.url}) {data["commit"]["message"]}\n{data["stats"]["additions"]} additions, {data["stats"]["deletions"]} deletions', url=rep.url)
                        embed.set_author(name=f'{data["commit"]["author"]["name"]}', url=f'{data["author"]["url"]}', icon_url=f'{data["author"]["avatar_url"]}')

                        for file in data['files']:
                            embed.add_field(name=file['filename'], value=f'{file["additions"]} additions, {file["deletions"]} deletions', inline=False)
                        
                        await channel.send(embed=embed)

            except:
                pass
            await asyncio.sleep(60)
    
    async def price_tracking_rs3(self):
        '''
        Function to automatically and constantly update item pricing
        '''
        await asyncio.sleep(5)
        print('Starting rs3 price tracking...')
        config = config_load()
        channel = self.get_channel(config['testChannel'])
        while True:
            try:
                items = await RS3Item.query.order_by(RS3Item.id.asc()).gino.all()
                items = sorted(items, key=lambda i: max([int(x) for x in i.graph_data['daily']]))
                for item in items:
                    # print(f'[RS3]  Refreshing price of {item.id}: {item.name}')
                    graph_url = f'http://services.runescape.com/m=itemdb_rs/api/graph/{item.id}.json'

                    graph_data = None

                    exists = True
                    while True:
                        r = await self.bot.aiohttp.get(graph_url)
                        async with r:
                            if r.status == 404:
                                logging.critical(f'RS3 404 error for item {item.id}: {item.name}')
                                try:
                                    await channel.send(f'RS3 404 error for item {item.id}: {item.name}')
                                except:
                                    print(f'RS3 404 error for item {item.id}: {item.name}')
                                exists = False
                                break
                            elif r.status != 200:
                                await asyncio.sleep(60)
                                continue
                            try:
                                graph_data = await r.json(content_type='text/html')
                                break
                            except:
                                print(e)
                                await asyncio.sleep(60)
                    
                    if not exists:
                        continue

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
                    
                    await item.update(current=str(current), today=str(today), day30=day30, day90=day90, day180=day180, graph_data=graph_data).apply()

                    await asyncio.sleep(5)
            except OSError as e:
                print(f'Error encountered in rs3 price tracking: {e}')
                logging.critical(f'Error encountered in rs3 price tracking: {e}')
                await asyncio.sleep(60)
            except Exception as e:
                error = f'Error encountered in rs3 price tracking: {e}'
                print(error)
                logging.critical(error)
                try:
                    await channel.send(error)
                except:
                    pass
                await asyncio.sleep(300)
    
    async def price_tracking_osrs(self):
        '''
        Function to automatically and constantly update item pricing
        '''
        await asyncio.sleep(5)
        print('Starting osrs price tracking...')
        config = config_load()
        channel = self.get_channel(config['testChannel'])
        while True:
            try:
                items = await OSRSItem.query.order_by(OSRSItem.id.asc()).gino.all()
                items = sorted(items, key=lambda i: max([int(x) for x in i.graph_data['daily']]))
                for item in items:
                    # print(f'[OSRS] Refreshing price of {item.id}: {item.name}')
                    graph_url = f'http://services.runescape.com/m=itemdb_oldschool/api/graph/{item.id}.json'

                    graph_data = None

                    exists = True
                    while True:
                        r = await self.bot.aiohttp.get(graph_url)
                        async with r:
                            if r.status == 404:
                                logging.critical(f'OSRS 404 error for item {item.id}: {item.name}')
                                try:
                                    await channel.send(f'OSRS 404 error for item {item.id}: {item.name}')
                                except:
                                    print(f'OSRS 404 error for item {item.id}: {item.name}')
                                exists = False
                                break
                            elif r.status != 200:
                                await asyncio.sleep(60)
                                continue
                            try:
                                graph_data = await r.json(content_type='text/html')
                                break
                            except Exception as e:
                                print(e)
                                await asyncio.sleep(60)
                    
                    if not exists:
                        continue

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
                    
                    await item.update(current=str(current), today=str(today), day30=day30, day90=day90, day180=day180, graph_data=graph_data).apply()

                    await asyncio.sleep(5)
            except OSError as e:
                print(f'Error encountered in osrs price tracking: {e}')
                logging.critical(f'Error encountered in osrs price tracking: {e}')
                await asyncio.sleep(60)
            except Exception as e:
                error = f'Error encountered in osrs price tracking: {e}'
                print(error)
                logging.critical(error)
                try:
                    await channel.send(error)
                except:
                    pass
                await asyncio.sleep(300)


if __name__ == '__main__':
    logging.basicConfig(filename='data/log.txt', level=logging.CRITICAL)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
