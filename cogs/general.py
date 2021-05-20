import discord
from discord.ext import commands
import sys
sys.path.append('../')
from main import config_load, addCommand, Poll
import math
import random
import re
import pyowm
from datetime import datetime, timedelta, timezone
from operator import attrgetter
import cmath
from utils import is_int, is_float
import codecs
import json
from utils import is_owner, is_admin, portables_admin, is_mod, is_rank, is_smiley, portables_only
import validators

config = config_load()

rps = ['Rock', 'Paper', 'Scissors']
rpsUpper = ['ROCK', 'PAPER', 'SCISSORS']

months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

owm = pyowm.OWM(config['weatherAPI'])

num_emoji = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯', '🇰', '🇱', '🇲', '🇳', '🇴', '🇵', '🇶', '🇷', '🇸', '🇹']

def perm_string(p):
    '''
    Translates permissions to a string of important permissions.
    '''
    s = ''

    if p.administrator:
        s += 'Administrator, '
    if p.manage_guild:
        s += 'Manage Server, '
    if p.ban_members:
        s += 'Ban Members, '
    if p.kick_members:
        s += 'Kick Members, '
    if p.manage_channels:
        s += 'Manage Channels, '
    if p.manage_messages:
        s += 'Manage Messages, '
    if p.mention_everyone:
        s += 'Mention Everyone, '
    if p.manage_nicknames:
        s += 'Manage Nicknames, '
    if p.manage_roles:
        s += 'Manage Roles, '
    if p.manage_emojis:
        s += 'Manage Emojis, '
    if p.manage_webhooks:
        s += 'Manage Webhooks, '
    if p.view_audit_log:
        s += 'View Audit Logs, '

    if s:
        s = s[:len(s)-2]

    return s

# Dict of latin words from latin wiktionary
def load_words():
    with codecs.open('data/loremIpsum.json', 'r', encoding='utf-8-sig') as doc:
        return json.load(doc)

# Create a simple list from the weirdly formatted dictionary, excluding non-alphabetic words
word_list = []
for lst in load_words()['*']:
    lst = lst['a']['*']
    for item in lst:
        word = item['title']
        if word.isalpha():
            word_list.append(word)

# Divide total number of words pseudo-randomly over number of paragraphs
def get_paragraph_lengths(paragraphs, words):
    lower = round(words/paragraphs/2) # minimum words per paragraph
    upper = round(words/paragraphs*2) # maximum words per paragraph
    lengths = random.sample(range(lower, upper), paragraphs)
    while sum(lengths) < words:
        lengths[random.randint(0, paragraphs-1)] += 1
    while sum(lengths) > words:
        lengths[random.randint(0, paragraphs-1)] -= 1
    return lengths

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, aliases=['flip', 'coin', 'coinflip'])
    async def flipcoin(self, ctx):
        '''
        Flips a coin.
        '''
        addCommand()
        
        i = random.randint(0,1)
        result = ''
        if i:
            result = 'heads'
        else:
            result = 'tails'
        
        await ctx.send(f'{ctx.author.mention} {result}!')

    @commands.command(pass_context=True, aliases=['dice'])
    async def roll(self, ctx, sides=6, num=1):
        '''
        Rolls a dice.
        '''
        addCommand()
        
        if is_int(num):
            num = int(num)
        else:
            raise commands.CommandError(message=f'Invalid argument: `{num}`.')
        if num < 1 or num > 100:
            raise commands.CommandError(message=f'Invalid argument: `{num}`.')
        if is_int(sides):
            sides = int(sides)
        else:
            raise commands.CommandError(message=f'Invalid argument: `{sides}`.')
        if sides < 2 or sides > 2147483647:
            raise commands.CommandError(message=f'Invalid argument: `{sides}`.')

        results = []
        for _ in range (0, num):
            results.append(random.randint(1,sides))
        result = str(results).replace('[', '').replace(']', '')
        
        await ctx.send(f'{ctx.author.mention} You rolled {result}!')

    @commands.command(pass_context=True)
    async def rps(self, ctx, choice=''):
        '''
        Play rock, paper, scissors.
        '''
        addCommand()
        
        if not choice.upper() in rpsUpper:
            raise commands.CommandError(message=f'Invalid argument: `{choice}`.')
        
        for x in rps:
            if choice.upper() == x.upper():
                choice = x
        i = random.randint(0,2)
        myChoice = rps[i]
        result = f'You chose **{choice}**. I choose **{myChoice}**.\n'
        choices = [myChoice, choice]
        if choice == myChoice:
            result += '**Draw!**'
        elif 'Rock' in choices and 'Paper' in choices:
            result += '**Paper** wins!'
        elif 'Rock' in choices and 'Scissors' in choices:
            result += '**Rock** wins!'
        elif 'Paper' in choices and 'Scissors' in choices:
            result += '**Scissors** win!'
        
        await ctx.send(result)

    @commands.command(pass_context=True, aliases=['forecast'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def weather(self, ctx, *locations):
        '''
        Get the weather forecast for a location
        '''
        addCommand()
        await ctx.channel.trigger_typing()
        
        location = ''
        for l in locations:
            location += l + ' '
        location = location.strip()
        if not location:
            raise commands.CommandError(message=f'Required argument missing: `location`.')

        try:
            observation = owm.weather_at_place(location)
        except:
            raise commands.CommandError(message=f'Error: could not find location: `{location}`.')
        w = observation.get_weather()
        temperature = w.get_temperature('celsius')
        wind = w.get_wind('meters_sec')

        title = f'Weather for: {observation.get_location().get_name()}, {observation.get_location().get_country()}'
        colour = 0x00b2ff
        timestamp = datetime.utcnow()
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp)
        embed.add_field(name='Condition:', value=f'{w.get_status()}')
        embed.add_field(name='Temperature:', value=f'Current: {temperature["temp"]}°C\nMax: {temperature["temp_max"]}°C\nMin: {temperature["temp_min"]}°C')
        embed.add_field(name='Wind speed:', value=f'{wind["speed"]*3.6} km/h')
        
        await ctx.send(embed=embed)

    @commands.command(pass_context=True)
    async def serverinfo(self, ctx):
        '''
        Get info on a server
        '''
        addCommand()

        guild = ctx.guild
        title = f'Server info for: **{guild.name}**'
        colour = 0x00b2ff
        timestamp = datetime.utcnow()
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp)
        embed.add_field(name='Owner', value=f'{guild.owner.name}#{guild.owner.discriminator}')
        embed.add_field(name='Region', value=f'{guild.region}')
        embed.add_field(name='Channels', value=f'{len(guild.channels)}')
        embed.add_field(name='Members', value=f'{guild.member_count}')
        embed.add_field(name='Roles', value=f'{len(guild.roles)}')
        icon = guild.icon_url
        if icon:
            embed.set_thumbnail(url=icon)
        embed.set_footer(text=f'ID: {guild.id}')

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, alias=['userinfo', 'memberinfo'])
    async def whois(self, ctx, *memberName):
        '''
        Get info on a member.
        '''
        addCommand()
        
        msg = ctx.message
        member = ''
        if msg.mentions:
            member = msg.mentions[0]
        else:
            if not memberName:
                raise commands.CommandError(message=f'Required argument missing: `member`.')
            else:
                name = ''
                for n in memberName:
                    name += n + ' '
                name = name.strip()
                for m in ctx.guild.members:
                    if m.name.upper() == name.upper():
                        member = m
                        break
                    nick = m.nick
                    if nick:
                        if nick.upper() == name.upper():
                            member = m
                            break
                if not member:
                    for m in ctx.guild.members:
                        if name.upper() in m.name.upper():
                            member = m
                            break
                        nick = m.nick
                        if nick:
                            if name.upper() in nick.upper():
                                member = m
                                break
        if not member:
            raise commands.CommandError(message=f'Error: could not find member: `{name}`.')

        member = await ctx.guild.fetch_member(member.id)

        colour = 0x00b2ff
        timestamp = datetime.utcnow()
        embed = discord.Embed(colour=colour, timestamp=timestamp, description=f'{member.mention}')
        if member.avatar_url:
            embed.set_author(name=f'{member.name}#{member.discriminator}', url=discord.Embed.Empty, icon_url=member.avatar_url)
            embed.set_thumbnail(url=member.avatar_url)
        else:
            embed.set_author(name=f'{member.name}#{member.discriminator}', url=discord.Embed.Empty, icon_url=member.default_avatar_url)
            embed.set_thumbnail(url=member.default_avatar_url)
        embed.add_field(name='Status', value=f'{str(member.status)[0].upper() + str(member.status)[1:]}')
        joinTime = member.joined_at
        min = joinTime.minute
        if min == 0:
            min = '00'
        time = f'{joinTime.day} {months[joinTime.month-1]} {joinTime.year}, {joinTime.hour}:{min}'
        embed.add_field(name='Joined', value=time)
        joinList = sorted(ctx.guild.members, key=attrgetter('joined_at'))
        joinPos = joinList.index(member)+1
        embed.add_field(name='Join Position', value=str(joinPos))
        creationTime = member.created_at
        min = creationTime.minute
        if min == 0:
            min = '00'
        time = f'{creationTime.day} {months[creationTime.month-1]} {creationTime.year}, {creationTime.hour}:{min}'
        embed.add_field(name='Registered', value=time)
        roles = member.roles
        roleStr = ''
        for i, r in enumerate(roles):
            if i == 0:
                continue
            roleStr += r.mention + ' '
        roleStr = roleStr.strip()
        if roleStr:
            embed.add_field(name=f'Roles ({len(member.roles)-1})', value=roleStr, inline=False)
        else:
            embed.add_field(name=f'Roles (0)', value='None', inline=False)
        permStr = perm_string(member.guild_permissions)
        if permStr:
            embed.add_field(name=f'Permissions', value=permStr)
        embed.set_footer(text=f'ID: {member.id}')

        await ctx.send(embed=embed)

    @commands.command()
    async def quote(self, ctx, msg_id=''):
        '''
        Quotes a message from a given message ID.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not msg_id:
            raise commands.CommandError(message=f'Required argument missing: `message_id`.')
        elif not is_int(msg_id):
            raise commands.CommandError(message=f'Invalid argument: `{msg_id}`.')
        else:
            msg_id = int(msg_id)
        
        chan = ''

        try:
            msg = await ctx.channel.fetch_message(msg_id)
            chan = ctx.channel
        except:
            msg = ''

        if not msg:
            for channel in ctx.guild.text_channels:
                try:
                    msg = await channel.fetch_message(msg_id)
                    chan = channel
                    break
                except:
                    msg = ''

        if not msg:
            raise commands.CommandError(message=f'Error: could not find message: `{msg_id}`.')

        embed = discord.Embed(description=f'In: {chan.mention}\n“{msg.content}”', colour=0x00b2ff, timestamp=msg.created_at)
        embed.set_author(name=f'{msg.author.display_name}#{msg.author.discriminator}', icon_url=msg.author.avatar_url)
        embed.set_footer(text=f'ID: {msg.id}')

        await ctx.message.delete()
        await ctx.send(embed=embed)

    @commands.command(aliases=['lorem', 'ipsum', 'loremipsum'])
    async def lipsum(self, ctx, words=0, paragraphs=1):
        '''
        Generate random Lorem Ipsum text.
        '''
        addCommand()

        # Verify that both the number of words and paragraphs are positive
        if words < 1:
            raise commands.CommandError(message=f'Invalid argument: `{words}`.')
        if paragraphs < 1:
            raise commands.CommandError(message=f'Invalid argument: `{paragraphs}`.')

        # Initialize variables
        text = ''
        paragraph_lengths = get_paragraph_lengths(paragraphs, words)
        sentence_length = random.randint(10, 30)
        punctuation = [', ', ', ', ', ', '; ', ': '] # comma is 3x more common

        for p in range(0, paragraphs):
            paragraph_length = paragraph_lengths[p] # get length for this paragraph

            word_num = 0
            for w in range(0, paragraph_length):
                word = word_list[random.randint(0, len(word_list)-1)] # get random word
                word_num += 1 # position of word in sentence

                # if new sentence, start with upper case, and choose sentence length
                if word_num % sentence_length == 1:
                    sentence_length = random.randint(10, 30)
                    word_num = 1
                    word = word[:1].upper() + word[1:]

                text += word

                # add punctuation and/or space
                if not w == paragraph_length-1:
                    if word_num == sentence_length:
                        text += '. '
                    elif not random.randint(0, 20):
                        text += punctuation[random.randint(0, len(punctuation)-1)]
                    else:
                        text += ' '
                else:
                    text += '.'

            # Add whitespace between paragraphs
            if not p == paragraphs-1:
                text += '\n\n'

        # Check if message length is OK
        if len(text) > 2048:
            raise commands.CommandError(message=f'Error: character limit exceeded.')

        # Create and send embed
        embed = discord.Embed(title='Lorem Ipsum', description=text, timestamp=datetime.utcnow())
        embed.set_author(name='Chatty', icon_url='https://i.imgur.com/hu3nR8o.png')
        embed.set_footer(text=f'{words} words, {paragraphs} paragraphs')
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def shorten(self, ctx, url=''):
        '''
        Shorten a URL.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not url:
            raise commands.CommandError(message='Required argument missing: `url`.')
        if not validators.url(url):
            raise commands.CommandError(message=f'Invalid argument: `{url}`. Argument must be a valid URL.')

        r = await self.bot.aiohttp.get(f'https://is.gd/create.php?format=simple&url={url}')
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving shortened URL, please try again in a minute.')
            data = await r.text()

        await ctx.send(data)
    
    @commands.command()
    async def id(self, ctx, *input):
        '''
        Get the ID of a discord object.
        It is best to provide a mention to ensure the right object is found.
        Supports: channels, roles, members, emojis, messages, guild.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not input:
            raise commands.CommandError(message='Required argument missing: `input`.')
        input = ' '.join(input)
        input_raw = input
        input = input.lower()
        output = ''
        output_type = ''
        backup = ''
        backup_type = ''

        # handle mentions / defaults
        if ctx.message.channel_mentions:
            output = ctx.message.channel_mentions[0]
            output_type = 'channel'
        elif ctx.message.role_mentions:
            output = ctx.message.role_mentions[0]
            output_type = 'role'
        elif ctx.message.mentions:
            output = ctx.message.mentions[0]
            output_type = 'member'
        elif input == ctx.guild.name.lower() or input == 'guild' or input == 'server':
            output = ctx.guild
            output_type = 'guild'
        elif input == 'owner':
            output = ctx.guild.owner
            output_type = 'member'
        elif input == 'me':
            output = ctx.message.author
            output_type = 'member'
        elif input == 'you' or input == 'u':
            output = ctx.guild.me
            output_type = 'member'
        
        # channels
        if not output:
            for channel in ctx.guild.channels:
                if channel.name.lower() == input:
                    output = channel
                    output_type = 'channel'
                    break
                elif not backup:
                    if input in channel.name.lower():
                        backup = channel
                        backup_type = 'channel'
        
        # roles
        if not output:
            for role in ctx.guild.roles:
                if role.name.lower() == input:
                    output = role
                    output_type = 'role'
                    break
                elif not backup:
                    if input in role.name.lower():
                        backup = role
                        backup_type = 'role'
        
        # members
        if not output:
            for member in ctx.guild.members:
                if member.display_name.lower() == input or member.name.lower() == input:
                    output = member
                    output_type = 'member'
                    break
                elif not backup:
                    if input in member.display_name.lower() or input in member.name.lower():
                        backup = member
                        backup_type = 'member'
        
        # emoji
        if not output:
            guild_emojis = await ctx.guild.fetch_emojis()
            for emoji in guild_emojis:
                if str(emoji) == input_raw or emoji.name.lower() == input:
                    output = emoji
                    output_type = 'emoji'
                    break
                elif not backup:
                    if input in emoji.name.lower():
                        backup = emoji
                        backup_type = 'emoji'
        
        # message
        if not output:
            for channel in ctx.guild.text_channels:
                async for message in channel.history(limit=100):
                    if message.guild == ctx.guild:
                        if input in message.content and not message.id == ctx.message.id:
                            output = message
                            output_type = 'message'
                            break
                if output:
                    break
        
        if output:
            if output_type in ['channel', 'role', 'member', 'emoji', 'guild']:
                await ctx.send(f'The ID for {output_type} `{output.name}` is: `{output.id}`.')
            else:
                await ctx.send(f'The ID for the following message, sent by `{output.author.display_name}` in {output.channel.mention} is: `{output.id}`.\n"{output.content}"')
        elif backup:
            await ctx.send(f'The ID for {backup_type} `{backup.name}` is: `{backup.id}`.')
        else:
            raise commands.CommandError(message=f'Error, could not find any object: `{input}`. Please check your spelling.')
    
    @commands.command(aliases=['strawpoll'])
    async def poll(self, ctx, hours='24', *options):
        '''
        Create a poll in which users can vote by reacting.
        Poll duration can vary from 1 hour to 1 week (168 hours).
        Options must be separated by commas.
        '''
        addCommand()

        if not is_int(hours):
            options = [hours] + list(options)
            hours = 24
        else:
            hours = int(hours)
        if hours < 1 or hours > 168:
            raise commands.CommandError(message=f'Invalid argument: `{hours}`. Must be positive and less than 168.')
        
        options = ' '.join(options)
        options = options.split(',')
        
        if len(options) < 2:
            raise commands.CommandError(message='Error: insufficient options to create a poll. At least two options are required.')
        elif len(options) > 20:
            raise commands.CommandError(message='Error: too many options. This command only supports up to 20 options.')

        txt = ''
        i = 0
        for opt in options:
            txt += f'\n{num_emoji[i]} {opt}'
            i += 1
        txt += f'\n\nThis poll will be open for {hours} hours!'
        
        embed = discord.Embed(title='**Poll**', description=f'Created by {ctx.message.author.mention}\n{txt}', timestamp=datetime.utcnow())
        
        msg = await ctx.send(embed=embed)
        embed.set_footer(text=f'ID: {msg.id}')
        await msg.edit(embed=embed)
        for num in range(i):
            await msg.add_reaction(num_emoji[num])
        
        await Poll.create(guild_id=ctx.guild.id, author_id=ctx.author.id, channel_id=ctx.channel.id, message_id=msg.id, end_time = datetime.utcnow()+timedelta(hours=hours))

    @commands.command()
    async def close(self, ctx, msg_id=''):
        '''
        Close a poll by giving its message ID.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not is_int(msg_id):
            raise commands.CommandError(message=f'Invalid argument: `{msg_id}`. Must be an integer.')
        msg_id = int(msg_id)

        poll = await Poll.query.where(Poll.message_id==msg_id).gino.first()
        if not poll:
            raise commands.CommandError(message=f'Could not find active poll by ID: `{msg_id}`.')

        if poll.author_id != ctx.message.author.id:
            raise commands.CommandError(message=f'Insufficient permissions: only the creator of the poll can close it prematurely.')

        await poll.delete()

        try: 
            msg = await ctx.guild.get_channel(poll.channel_id).fetch_message(msg_id)
        except:
            raise commands.CommandError(message=f'Error: could not find message: `{msg_id}`. Was the poll deleted?')
        
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

        txt = ''
        for emoji, score in results.items():
            txt += f'{emoji}: {score}\n'
        if not tie:
            txt += f'\nOption {winner} won with {percentage}% of the votes!'
        else:
            txt += f'It\'s a tie! Options {winner} each have {percentage}% of the votes!'
        embed = discord.Embed(title='**Poll Results**', description=txt, timestamp=datetime.utcnow())
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(General(bot))
