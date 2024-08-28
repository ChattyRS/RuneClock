import discord
from discord.ext import commands
from discord.ext.commands import Cog
import sys
sys.path.append('../')
from main import Bot, get_config, increment_command_counter, Poll
import random
from datetime import datetime, timedelta, UTC
from operator import attrgetter
from utils import is_int
import validators

config = get_config()

rps = ['Rock', 'Paper', 'Scissors']
rps_upper = ['ROCK', 'PAPER', 'SCISSORS']

months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

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

class General(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(pass_context=True, aliases=['flip', 'coin', 'coinflip'])
    async def flipcoin(self, ctx: commands.Context):
        '''
        Flips a coin.
        '''
        increment_command_counter()
        
        i = random.randint(0,1)
        result = ''
        if i:
            result = 'heads'
        else:
            result = 'tails'
        
        await ctx.send(f'{ctx.author.mention} {result}!')

    @commands.command(pass_context=True, aliases=['dice'])
    async def roll(self, ctx: commands.Context, sides=6, num=1):
        '''
        Rolls a dice.
        '''
        increment_command_counter()
        
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
    async def rps(self, ctx: commands.Context, choice=''):
        '''
        Play rock, paper, scissors.
        '''
        increment_command_counter()
        
        if not choice.upper() in rps_upper:
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

    @commands.command(pass_context=True)
    async def serverinfo(self, ctx: commands.Context):
        '''
        Get info on a server
        '''
        increment_command_counter()

        title = f'Server info for: **{ctx.guild.name}**'
        colour = 0x00b2ff
        timestamp = datetime.now(UTC)
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp)
        embed.add_field(name='Owner', value=ctx.guild.owner.mention)
        embed.add_field(name='Channels', value=f'{len(ctx.guild.channels)}')
        embed.add_field(name='Members', value=f'{ctx.guild.member_count}')
        embed.add_field(name='Roles', value=f'{len(ctx.guild.roles)}')
        icon = ctx.guild.icon.url
        if icon:
            embed.set_thumbnail(url=icon)
        embed.set_footer(text=f'ID: {ctx.guild.id}')

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, alias=['userinfo', 'memberinfo'])
    async def whois(self, ctx: commands.Context, *memberName):
        '''
        Get info on a member.
        '''
        increment_command_counter()
        
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

        members = await ctx.guild.query_members(user_ids=[member.id], presences=True)
        member = members[0]

        colour = 0x00b2ff
        timestamp = datetime.now(UTC)
        embed = discord.Embed(colour=colour, timestamp=timestamp, description=f'{member.mention}')
        if member.display_avatar.url:
            embed.set_author(name=member.name, url=None, icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name='Display name', value=member.display_name)
        embed.add_field(name='Status', value=f'{str(member.status)[0].upper() + str(member.status)[1:]}')
        join_time = member.joined_at
        min = join_time.minute
        if min == 0:
            min = '00'
        time = f'{join_time.day} {months[join_time.month-1]} {join_time.year}, {join_time.hour}:{min}'
        embed.add_field(name='Joined', value=time)
        join_list = sorted(ctx.guild.members, key=attrgetter('joined_at'))
        join_pos = join_list.index(member)+1
        embed.add_field(name='Join Position', value=str(join_pos))
        creation_time = member.created_at
        min = creation_time.minute
        if min == 0:
            min = '00'
        time = f'{creation_time.day} {months[creation_time.month-1]} {creation_time.year}, {creation_time.hour}:{min}'
        embed.add_field(name='Registered', value=time)
        roles = member.roles
        role_str = ''
        for i, r in enumerate(roles):
            if i == 0:
                continue
            role_str += r.mention + ' '
        role_str = role_str.strip()
        if role_str:
            embed.add_field(name=f'Roles ({len(member.roles)-1})', value=role_str, inline=False)
        else:
            embed.add_field(name=f'Roles (0)', value='None', inline=False)
        perm_str = perm_string(member.guild_permissions)
        if perm_str:
            embed.add_field(name=f'Permissions', value=perm_str)
        embed.set_footer(text=f'ID: {member.id}')

        await ctx.send(embed=embed)

    @commands.command()
    async def quote(self, ctx: commands.Context, msg_id=''):
        '''
        Quotes a message from a given message ID.
        '''
        increment_command_counter()
        await ctx.channel.typing()

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
        embed.set_author(name=msg.author.display_name, icon_url=msg.author.display_avatar.url)
        embed.set_footer(text=f'ID: {msg.id}')

        await ctx.message.delete()
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def shorten(self, ctx: commands.Context, url=''):
        '''
        Shorten a URL.
        '''
        increment_command_counter()
        await ctx.channel.typing()

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
    async def id(self, ctx: commands.Context, *input):
        '''
        Get the ID of a discord object.
        It is best to provide a mention to ensure the right object is found.
        Supports: channels, roles, members, emojis, messages, guild.
        '''
        increment_command_counter()
        await ctx.channel.typing()

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
    async def poll(self, ctx: commands.Context, hours='24', *options):
        '''
        Create a poll in which users can vote by reacting.
        Poll duration can vary from 1 hour to 1 week (168 hours).
        Options must be separated by commas.
        '''
        increment_command_counter()

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
        
        embed = discord.Embed(title='**Poll**', description=f'Created by {ctx.message.author.mention}\n{txt}', timestamp=datetime.now(UTC))
        
        msg = await ctx.send(embed=embed)
        embed.set_footer(text=f'ID: {msg.id}')
        await msg.edit(embed=embed)
        for num in range(i):
            await msg.add_reaction(num_emoji[num])
        
        await Poll.create(guild_id=ctx.guild.id, author_id=ctx.author.id, channel_id=ctx.channel.id, message_id=msg.id, end_time = datetime.now(UTC)+timedelta(hours=hours))

    @commands.command()
    async def close(self, ctx: commands.Context, msg_id=''):
        '''
        Close a poll by giving its message ID.
        '''
        increment_command_counter()
        await ctx.channel.typing()

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
        embed = discord.Embed(title='**Poll Results**', description=txt, timestamp=datetime.now(UTC))
        await ctx.send(embed=embed)


async def setup(bot: Bot):
    await bot.add_cog(General(bot))
