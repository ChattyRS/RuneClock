from typing import Any
from aiohttp import ClientResponse
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from sqlalchemy import select
from main import Bot
from database import Poll
import random
from datetime import datetime, timedelta, UTC
from operator import attrgetter
from utils import is_int
import validators

rps: list[str] = ['Rock', 'Paper', 'Scissors']
rps_upper: list[str] = ['ROCK', 'PAPER', 'SCISSORS']

months: list[str] = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

num_emoji: list[str] = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯', '🇰', '🇱', '🇲', '🇳', '🇴', '🇵', '🇶', '🇷', '🇸', '🇹']

def perm_string(p) -> str:
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
        s: str = s[:len(s)-2]

    return s

class General(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @commands.command(pass_context=True, aliases=['flip', 'coin', 'coinflip'])
    async def flipcoin(self, ctx: commands.Context) -> None:
        '''
        Flips a coin.
        '''
        self.bot.increment_command_counter()
        
        i: int = random.randint(0,1)
        result: str
        if i:
            result = 'heads'
        else:
            result = 'tails'
        
        await ctx.send(f'{ctx.author.mention} {result}!')

    @commands.command(pass_context=True, aliases=['dice'])
    async def roll(self, ctx: commands.Context, sides=6, num=1) -> None:
        '''
        Rolls a dice.
        '''
        self.bot.increment_command_counter()
        
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

        results: list[int] = []
        for _ in range (0, num):
            results.append(random.randint(1,sides))
        result: str = str(results).replace('[', '').replace(']', '')
        
        await ctx.send(f'{ctx.author.mention} You rolled {result}!')

    @commands.command(pass_context=True)
    async def rps(self, ctx: commands.Context, choice='') -> None:
        '''
        Play rock, paper, scissors.
        '''
        self.bot.increment_command_counter()
        
        if not choice.upper() in rps_upper:
            raise commands.CommandError(message=f'Invalid argument: `{choice}`.')
        
        for x in rps:
            if choice.upper() == x.upper():
                choice = x
        i: int = random.randint(0,2)
        myChoice: str = rps[i]
        result: str = f'You chose **{choice}**. I choose **{myChoice}**.\n'
        choices: list[str] = [myChoice, choice]
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
    async def serverinfo(self, ctx: commands.Context) -> None:
        '''
        Get info on a server
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')

        title: str = f'Server info for: **{ctx.guild.name}**'
        colour = 0x00b2ff
        timestamp = datetime.now(UTC)
        embed = discord.Embed(title=title, colour=colour, timestamp=timestamp)
        if ctx.guild.owner:
            embed.add_field(name='Owner', value=ctx.guild.owner.mention)
        embed.add_field(name='Channels', value=f'{len(ctx.guild.channels)}')
        embed.add_field(name='Members', value=f'{ctx.guild.member_count}')
        embed.add_field(name='Roles', value=f'{len(ctx.guild.roles)}')
        if ctx.guild.icon and ctx.guild.icon.url:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.set_footer(text=f'ID: {ctx.guild.id}')

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, alias=['userinfo', 'memberinfo'])
    async def whois(self, ctx: commands.Context, *member_name) -> None:
        '''
        Get info on a member.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')
        
        member: discord.Member | discord.User | str = ''
        if ctx.message.mentions:
            member = ctx.message.mentions[0]
        else:
            if not member_name:
                raise commands.CommandError(message=f'Required argument missing: `member`.')
            else:
                name: str = ''
                for n in member_name:
                    name += n + ' '
                name = name.strip()
                for m in ctx.guild.members:
                    if m.name.upper() == name.upper():
                        member = m
                        break
                    nick: str | None = m.nick
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

        members: list[discord.Member] = await ctx.guild.query_members(user_ids=[member.id], presences=True)
        member = members[0]

        colour = 0x00b2ff
        timestamp: datetime = datetime.now(UTC)
        embed = discord.Embed(colour=colour, timestamp=timestamp, description=f'{member.mention}')
        if member.display_avatar.url:
            embed.set_author(name=member.name, url=None, icon_url=member.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name='Display name', value=member.display_name)
        embed.add_field(name='Status', value=f'{str(member.status)[0].upper() + str(member.status)[1:]}')
        join_time: datetime | None = member.joined_at if member.joined_at else timestamp
        min: int | str = join_time.minute
        if min == 0:
            min = '00'
        time: str = f'{join_time.day} {months[join_time.month-1]} {join_time.year}, {join_time.hour}:{min}'

        embed.add_field(name='Joined', value=time)
        join_list = sorted(ctx.guild.members, key=attrgetter('joined_at'))
        join_pos = join_list.index(member)+1
        embed.add_field(name='Join Position', value=str(join_pos))
        creation_time: datetime = member.created_at
        min = creation_time.minute
        if min == 0:
            min = '00'
        time = f'{creation_time.day} {months[creation_time.month-1]} {creation_time.year}, {creation_time.hour}:{min}'
        embed.add_field(name='Registered', value=time)
        role_str: str = ''
        for i, r in enumerate(member.roles):
            if i == 0:
                continue
            role_str += r.mention + ' '
        role_str = role_str.strip()
        if role_str:
            embed.add_field(name=f'Roles ({len(member.roles)-1})', value=role_str, inline=False)
        else:
            embed.add_field(name=f'Roles (0)', value='None', inline=False)
        perm_str: str = perm_string(member.guild_permissions)
        if perm_str:
            embed.add_field(name=f'Permissions', value=perm_str)
        embed.set_footer(text=f'ID: {member.id}')

        await ctx.send(embed=embed)

    @commands.command()
    async def quote(self, ctx: commands.Context, msg_id='') -> None:
        '''
        Quotes a message from a given message ID.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
            raise commands.CommandError(message=f'This command can only be used from a server.')
        
        if not msg_id:
            raise commands.CommandError(message=f'Required argument missing: `message_id`.')
        elif not is_int(msg_id):
            raise commands.CommandError(message=f'Invalid argument: `{msg_id}`.')
        else:
            msg_id = int(msg_id)

        await ctx.channel.typing()
        
        channel: discord.TextChannel | None = None

        try:
            msg: discord.Message | None = await ctx.channel.fetch_message(msg_id)
            channel = ctx.channel
        except:
            msg = None

        if not msg:
            for channel in ctx.guild.text_channels:
                try:
                    msg = await channel.fetch_message(msg_id)
                    channel = msg.channel if isinstance(msg.channel, discord.TextChannel) else None
                    break
                except:
                    msg = None

        if not msg or not channel:
            raise commands.CommandError(message=f'Error: could not find message: `{msg_id}`.')

        embed = discord.Embed(description=f'In: {channel.mention}\n“{msg.content}”', colour=0x00b2ff, timestamp=msg.created_at)
        embed.set_author(name=msg.author.display_name, icon_url=msg.author.display_avatar.url)
        embed.set_footer(text=f'ID: {msg.id}')

        await ctx.message.delete()
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def shorten(self, ctx: commands.Context, url='') -> None:
        '''
        Shorten a URL.
        '''
        self.bot.increment_command_counter()

        if not url:
            raise commands.CommandError(message='Required argument missing: `url`.')
        if not validators.url(url):
            raise commands.CommandError(message=f'Invalid argument: `{url}`. Argument must be a valid URL.')
        
        await ctx.channel.typing()

        r: ClientResponse = await self.bot.aiohttp.get(f'https://is.gd/create.php?format=simple&url={url}')
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving shortened URL, please try again in a minute.')
            data: str = await r.text()

        await ctx.send(data)
    
    @commands.command()
    async def id(self, ctx: commands.Context, *input) -> None:
        '''
        Get the ID of a discord object.
        It is best to provide a mention to ensure the right object is found.
        Supports: channels, roles, members, emojis, messages, guild.
        '''
        self.bot.increment_command_counter()

        if not input:
            raise commands.CommandError(message='Required argument missing: `input`.')
        
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
            raise commands.CommandError(message=f'This command can only be used from a server.')
        
        await ctx.channel.typing()

        input_str: str = ' '.join(input)
        input_raw: str = input_str
        input_str = input_str.lower()

        output: Any = None
        output_type: str
        fallback: Any = None
        fallback_type: str

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
        elif input_str == ctx.guild.name.lower() or input_str == 'guild' or input_str == 'server':
            output = ctx.guild
            output_type = 'guild'
        elif input_str == 'owner':
            output = ctx.guild.owner
            output_type = 'member'
        elif input_str == 'me':
            output = ctx.message.author
            output_type = 'member'
        elif input_str == 'you' or input_str == 'u':
            output = ctx.guild.me
            output_type = 'member'
        
        # channels
        if not output:
            for channel in ctx.guild.text_channels:
                if channel.name.lower() == input_str:
                    output = channel
                    output_type = 'channel'
                    break
                elif not fallback:
                    if input_str in channel.name.lower():
                        fallback = channel
                        fallback_type = 'channel'
        
        # roles
        if not output:
            for role in ctx.guild.roles:
                if role.name.lower() == input_str:
                    output = role
                    output_type = 'role'
                    break
                elif not fallback:
                    if input_str in role.name.lower():
                        fallback = role
                        fallback_type = 'role'
        
        # members
        if not output:
            for member in ctx.guild.members:
                if member.display_name.lower() == input_str or member.name.lower() == input_str:
                    output = member
                    output_type = 'member'
                    break
                elif not fallback:
                    if input_str in member.display_name.lower() or input_str in member.name.lower():
                        fallback = member
                        fallback_type = 'member'
        
        # emoji
        if not output:
            guild_emojis = await ctx.guild.fetch_emojis()
            for emoji in guild_emojis:
                if str(emoji) == input_raw or emoji.name.lower() == input_str:
                    output = emoji
                    output_type = 'emoji'
                    break
                elif not fallback:
                    if input_str in emoji.name.lower():
                        fallback = emoji
                        fallback_type = 'emoji'
        
        # message
        if not output:
            for channel in ctx.guild.text_channels:
                async for message in channel.history(limit=100):
                    if message.guild == ctx.guild:
                        if input_str in message.content and not message.id == ctx.message.id:
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
        elif fallback:
            await ctx.send(f'The ID for {fallback_type} `{fallback.name}` is: `{fallback.id}`.')
        else:
            raise commands.CommandError(message=f'Error, could not find any object: `{input_str}`. Please check your spelling.')
    
    @commands.command(aliases=['strawpoll'])
    async def poll(self, ctx: commands.Context, hours='24', *options) -> None:
        '''
        Create a poll in which users can vote by reacting.
        Poll duration can vary from 1 hour to 1 week (168 hours).
        Options must be separated by commas.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')

        if not is_int(hours):
            options = [hours] + list(options)
            hours = 24
        else:
            hours = int(hours)
        if hours < 1 or hours > 168:
            raise commands.CommandError(message=f'Invalid argument: `{hours}`. Must be positive and less than 168.')
        
        options_str: str = ' '.join(options)
        options = options_str.split(',')
        
        if len(options) < 2:
            raise commands.CommandError(message='Error: insufficient options to create a poll. At least two options are required.')
        elif len(options) > 20:
            raise commands.CommandError(message='Error: too many options. This command only supports up to 20 options.')

        txt: str = ''
        i = 0
        for opt in options:
            txt += f'\n{num_emoji[i]} {opt}'
            i += 1
        txt += f'\n\nThis poll will be open for {hours} hours!'
        
        embed = discord.Embed(title='**Poll**', description=f'Created by {ctx.message.author.mention}\n{txt}', timestamp=datetime.now(UTC))
        
        msg: discord.Message = await ctx.send(embed=embed)
        embed.set_footer(text=f'ID: {msg.id}')
        await msg.edit(embed=embed)
        for num in range(i):
            await msg.add_reaction(num_emoji[num])

        async with self.bot.async_session() as session:
            session.add(Poll(guild_id=ctx.guild.id, author_id=ctx.author.id, channel_id=ctx.channel.id, message_id=msg.id, end_time = datetime.now(UTC)+timedelta(hours=hours)))
            await session.commit()

    @commands.command()
    async def close(self, ctx: commands.Context, msg_id='') -> None:
        '''
        Close a poll by giving its message ID.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used from a server.')

        if not is_int(msg_id):
            raise commands.CommandError(message=f'Invalid argument: `{msg_id}`. Must be an integer.')
        msg_id = int(msg_id)

        await ctx.channel.typing()

        async with self.bot.async_session() as session:
            poll: Poll | None = (await session.execute(select(Poll).where(Poll.message_id == msg_id))).scalar_one_or_none()
            if not poll:
                raise commands.CommandError(message=f'Could not find active poll by ID: `{msg_id}`.')

            if poll.author_id != ctx.message.author.id:
                raise commands.CommandError(message=f'Insufficient permissions: only the creator of the poll can close it prematurely.')

            await session.delete(poll)
            await session.commit()

        try: 
            channel: discord.TextChannel = self.bot.get_guild_text_channel(ctx.guild, poll.channel_id)
            msg: discord.Message = await channel.fetch_message(msg_id)
        except:
            raise commands.CommandError(message=f'Error: could not find message: `{msg_id}`. Was the poll deleted?')
        
        results: dict[str, int] = {}
        votes = 0
        for reaction in msg.reactions:
            results[str(reaction.emoji)] = reaction.count - 1
            votes += reaction.count - 1
        max_score = 0
        winner: str = ''
        tie = False
        for emoji, score in results.items():
            if score > max_score:
                max_score: int = score
                winner = emoji
                tie = False
            elif score == max_score:
                tie = True
                winner += f' and {emoji}'
        percentage = int((max_score)/max(1,votes)*100)

        embed: discord.Embed = msg.embeds[0]
        if not tie:
            embed.add_field(name='Results', value=f'Option {winner} won with {percentage}% of the votes!')
        else:
            embed.add_field(name='Results', value=f'It\'s a tie! Options {winner} each have {percentage}% of the votes!')
        await msg.edit(embed=embed)

        txt: str = ''
        for emoji, score in results.items():
            txt += f'{emoji}: {score}\n'
        if not tie:
            txt += f'\nOption {winner} won with {percentage}% of the votes!'
        else:
            txt += f'It\'s a tie! Options {winner} each have {percentage}% of the votes!'
        embed = discord.Embed(title='**Poll Results**', description=txt, timestamp=datetime.now(UTC))
        await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    await bot.add_cog(General(bot))
