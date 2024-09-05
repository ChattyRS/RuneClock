from typing import Sequence, Tuple
import discord
from discord.ext import commands
from discord.ext.commands import Cog, CommandError, Context
from sqlalchemy import select
from bot import Bot
from database import Command
import re
from checks import is_admin
from number_utils import is_int
from discord_utils import get_custom_command
from database_utils import get_custom_db_commands, find_custom_db_command

class CustomCommands(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
        self.bot.loop.create_task(self.refresh_custom_command_aliases())

    async def get_aliases(self) -> list[str]:
        aliases: list[str] = []
        async with self.bot.async_session() as session:
            custom_commands: Sequence[Command] = (await session.execute(select(Command))).scalars().all()
            for command in [c for c in custom_commands if c]:
                if not command.name in aliases:
                    aliases.append(command.name)
                if command.aliases:
                    for alias in command.aliases:
                        if not alias in aliases:
                            aliases.append(alias)
            return aliases
    
    async def refresh_custom_command_aliases(self) -> None:
        custom_command: commands.Command = get_custom_command(self.bot)
        self.bot.remove_command(custom_command.name)
        custom_command.aliases = await self.get_aliases()
        self.bot.add_command(custom_command)

    @commands.command()
    @is_admin()
    async def custom(self, ctx: Context) -> None:
        '''
        Command to add/remove custom commands. (Admin+)
        Arguments: name, response.
        Constraints: name can only contain alphanumeric characters.
        Not giving a response will remove the command.
        Special usage:
        {user} will add the name of the user.
        {server} will add the name of the server.
        {channel} will add the name of the channel.
        {@user} will mention a user by their username (not nickname).
        {&role} will add a mention for a specific role by name.
        {#channel} will add a mention of a specific channel by name.
        {#channelID} will add a mention of a specific channel by ID.
        $N is a basic variable. It returns the N-th argument given to the command when called. (Counting starts at 0).
        $N+ returns not just the N-th argument, but also all arguments that follow. (Counting starts at 0).
        {delete} will delete the message.
        {require:role} restricts usage of the command to users with a specific role by name.
        {!command} calls a built-in bot command (no custom commands).
        '''
        self.bot.increment_command_counter()
        if not ctx.guild:
            raise CommandError(message=f'This command can only be used from a server.')

        command: str = ctx.message.clean_content[ctx.message.clean_content.index(' ')+1:].strip()
        if ''.join(command.split()) == command:
            custom_db_command: Command | None
            async with self.bot.async_session() as session:
                custom_db_command = (await session.execute(select(Command).where(Command.guild_id == ctx.guild.id).where(Command.name == command))).scalar_one_or_none()
                if custom_db_command:
                    await session.delete(custom_db_command)
                    await session.commit()
                    custom_command: commands.Command = get_custom_command(self.bot)
                    self.bot.remove_command(custom_command.name)
                    custom_command.aliases = await self.get_aliases()
                    self.bot.add_command(custom_command)
                    await ctx.send(f'Command `{command}` has been removed.')
                    return
            raise CommandError(message=f'Please specify what your command should do. See `help custom`.')
        else:
            name: str = command.split()[0].lower()
            command = command.replace(name, '', 1).strip()

        cmd: commands.Command | None = self.bot.get_command(name)
        custom_command: commands.Command = get_custom_command(self.bot)
        if cmd and cmd != custom_command:
            raise CommandError(message=f'Command name `{name}` is already taken, please choose a different one.')
        
        async with self.bot.async_session() as session:
            custom_db_command: Command | None = (await session.execute(select(Command).where(Command.guild_id == ctx.guild.id).where(Command.name == command))).scalar_one_or_none()
            if custom_db_command:
                edit = True
                custom_db_command.function = command
            else:
                edit = False
                session.add(Command(guild_id=ctx.guild.id, name=name, function=command, aliases=None, description='N/A'))
            await session.commit()

        if not cmd: # alias didn't exist yet, so we need to add it
            custom_command = get_custom_command(self.bot)
            self.bot.remove_command(custom_command.name)
            custom_command.aliases = await self.get_aliases()
            self.bot.add_command(custom_command)

        if edit:
            await ctx.send(f'Edited command `{name}` to:\n```{command}```')
        else:
            await ctx.send(f'Added command `{name}`:\n```{command}```')


    @commands.command(hidden=True)
    async def custom_command(self, ctx: commands.Context, *args) -> None:
        '''
        Internal function used to call custom commands.
        Do not call this command directly.
        '''
        if not ctx.invoked_with or not ctx.guild or not isinstance(ctx.channel, discord.TextChannel) or not isinstance(ctx.author, discord.Member):
            raise CommandError(message=f'Could not find the guild, channel, or alias that was used to invoke the command. This is unexpected.')
        alias: str = ctx.invoked_with.lower()
        custom_db_command: Command | None = await find_custom_db_command(self.bot, ctx.guild, alias)
        if not custom_db_command:
            return
        
        command: str = custom_db_command.function

        self.bot.increment_command_counter()

        # {require:RoleName} makes this custom command only usable by members who have a role with the given name
        while '{require:' in command:
            begin: int = command.index('{require:')
            end: int = command.find('}', begin)
            if end == -1:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            input: str = command[begin+9:end]
            role_name: str = input.strip()
            role: discord.Role | None = discord.utils.find(lambda r: r.name == role_name, ctx.guild.roles)
            if not role:
                raise CommandError(message=f'Missing role: `{str(role_name)}`. Please verify that the role name is spelled correctly.')
            command = command.replace('{require:' + input + '}', '')
            if not role in ctx.author.roles:
                raise CommandError(message=f'Insufficient permissions: `{role_name}`.')

        # {user} will add the name of the user calling the command
        command = command.replace('{user}', ctx.author.name)

        # {server} will add the name of the server the command was called from
        command = command.replace('{server}', ctx.guild.name)

        # {channel} will add the name of the channel in which the command was called
        command = command.replace('{channel}', ctx.channel.name)

        # $N is a basic variable. It returns the N-th argument given to the command when called
        # $N+ returns not just the N-th argument, but also all arguments that follow
        if '$' in command:
            to_replace: list[(Tuple[str, str])] = []
            indices: list[int] = [m.start() for m in re.finditer(r'\$', command)]
            for index in indices:
                end = min(command.find(' ', index), command.find('}', index))
                if end == -1:
                    end = len(command)
                number: str | int = command[index+1:end].replace('}', '')
                if not number:
                    continue
                plus = False
                if '+' in number:
                    plus = True
                    number = number.replace('+', '')
                if not is_int(number):
                    continue
                number = int(number)
                if not plus:
                    try:
                        arg: str = args[number]
                        to_replace.append(('$' + str(number), arg))
                        continue
                    except:
                        raise CommandError(message=f'Error: required arguments missing. Use `help {alias}`.')
                else:
                    arguments: list[str] = []
                    for i, arg in enumerate(args):
                        if i >= number:
                            arguments.append(arg)
                    if not arguments and number != 0:
                        raise CommandError(message=f'Error: required arguments missing. Use `help {alias}`.')
                    arg_string: str = ''
                    for arg in arguments:
                        arg_string += arg + ' '
                    arg_string = arg_string.strip()
                    to_replace.append(('$' + str(number) + '+', arg_string))
                    continue
            if to_replace:
                for tuple in to_replace:
                    old: str = tuple[0]
                    new: str = tuple[1]
                    command = command.replace(old, new)

        # {@user} will mention a user by their username (not nickname)
        while '{@' in command:
            begin = command.index('{@')
            end = command.find('}', begin)
            if end == -1:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            input = command[begin+2:end]
            user_name: str = input.strip()
            member: discord.Member | None = discord.utils.find(lambda m: m.name == user_name, ctx.guild.members)
            if not member:
                raise CommandError(message=f'Missing user: `{user_name}`.')
            command = command.replace('{@' + input + '}', member.mention)

        # {&role} will add a mention for a specific role by name
        while '{&' in command:
            begin = command.index('{&')
            end = command.find('}', begin)
            if end == -1:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            input = command[begin+2:end]
            role_name = input.strip()
            role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
            if not role:
                raise CommandError(message=f'Missing role: `{role_name}`.')
            command = command.replace('{&' + input + '}', role.mention)

        # {#channel} will add a mention of a specific channel by name
        # {#channelID} will add a mention of a specific channel by ID
        while '{#' in command:
            begin = command.index('{#')
            end = command.find('}', begin)
            if end == -1:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            input = command[begin+2:end]
            channel_name: str = input.strip()
            channel: discord.VoiceChannel | discord.StageChannel | discord.ForumChannel | discord.TextChannel | discord.CategoryChannel | None = discord.utils.find(lambda c: str(c.id) == channel_name, ctx.guild.channels)
            if not channel:
                channel = discord.utils.find(lambda c: c.name == channel_name, ctx.guild.channels)
            if not channel:
                raise CommandError(message=f'Missing channel: `{channel_name}`.')
            command = command.replace('{#' + input + '}', channel.mention)

        # {!command} calls a built-in bot command (no custom commands)
        while '{!' in command:
            begin = command.index('{!')
            end = command.find('}', begin)
            if end == -1:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            command_string: str = command[begin+2:end]
            command = command.replace('{!' + command_string + '}', '')
            space: int = command_string.find(' ')
            if space == -1:
                space = len(command_string)
            commandName: str = command_string[:space]
            if commandName == 'customCommand':
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            command_arguments: str = command_string[space:]
            cmd: commands.Command | None = self.bot.get_command(commandName)
            if not cmd:
                raise CommandError(message=f'Missing command: `{commandName}`.')
            custom_command: commands.Command | None = get_custom_command(self.bot)
            if cmd == custom_command:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            arguments = command_arguments.split()
            try:
                for check in cmd.checks:
                    if not await check(ctx): # type: ignore MaybeCoro can be awaited
                        raise CommandError(message='Error: `Insufficient permissions`.')
                await cmd.callback(self, ctx, *arguments) # type: ignore MaybeCoro can be awaited
            except Exception as e:
                raise CommandError(message=f'Error: `{type(e).__name__} : {e}`.')

        # {delete} will delete the message
        if '{delete}' in command:
            try:
                await ctx.message.delete()
                command = command.replace('{delete}', '')
            except discord.Forbidden:
                raise CommandError(message=f'Missing permissions: `delete_message`.')
            except:
                command = command.replace('{delete}', '')

        command = command.strip()
        if command:
            await ctx.send(command)

    @commands.command(name='commands')
    async def _commands(self, ctx: commands.Context) -> None:
        '''
        Returns list of custom commands.
        '''
        self.bot.increment_command_counter()

        embed = discord.Embed(title='Commands')
        custom_commands: Sequence[Command] = await get_custom_db_commands(self.bot, ctx.guild)

        if not custom_commands:
            raise CommandError(message=f'This server does not have any custom commands.')
    
        for command in custom_commands:
            txt: str = ''
            if command.aliases:
                txt += 'Aliases: '
                for i, alias in enumerate(command.aliases):
                    txt += f'`{alias}`'
                    if i < len(command.aliases)-1:
                        txt += ' | '
            if len(command.function) <= 40:
                txt += f'\n`{command.function}`'
            else:
                txt += f'\n`{command.function[:20]}...`'
            if command.description:
                if not command.description == 'N/A':
                    if len(command.description) <= 80:
                        txt += f'\n{command.description}'
                    else:
                        txt += f'\n{command.description[:50]}...'
            if len(embed.fields) < 25:
                embed.add_field(name=command.name, value=txt, inline=False)
            else:
                try:
                    await ctx.send(embed=embed)
                except:
                    raise CommandError(message=f'Error: `character limit exceeded`.')
                embed.clear_fields()
                embed.add_field(name=command.name, value=txt, inline=False)

        try:
            await ctx.send(embed=embed)
        except:
            raise CommandError(message=f'Error: `character limit exceeded`.')

    @commands.command(aliases=['description'])
    @is_admin()
    async def describe(self, ctx: commands.Context, command='', *description) -> None:
        '''
        Add a short description to a custom command (Admin+).
        '''
        self.bot.increment_command_counter()

        if not command or not description:
            raise CommandError(message=f'Error: `required arguments missing`')
        
        description_str: str = ' '.join(description)

        async with self.bot.async_session() as session:
            custom_command: Command | None = await find_custom_db_command(self.bot, ctx.guild, command, session)
            if not custom_command:
                raise CommandError(message=f'Error: no such command: `{command}`.')

            custom_command.description = description_str
            await session.commit()

        await ctx.send(f'Your discription has been added to `{command}`.')

    @commands.command(name='alias')
    @is_admin()
    async def _alias(self, ctx: commands.Context, command='', alias='') -> None:
        '''
        Add/remove an alias for a custom command (Admin+).
        '''
        self.bot.increment_command_counter()

        if not command or not alias:
            raise CommandError(message=f'Error: `required arguments missing`.')

        cmd: commands.Command | None = self.bot.get_command(alias)
        custom_command: commands.Command | None = get_custom_command(self.bot)
        if cmd and cmd != custom_command:
            raise CommandError(message=f'Error: `alias already in use`.')
        
        msg: str = ''
        async with self.bot.async_session() as session:
            custom_db_command: Command | None = await find_custom_db_command(self.bot, ctx.guild, command, session)
            if not custom_db_command:
                raise CommandError(message=f'Error: no such command: `{command}`.')

            if custom_db_command.aliases:
                if alias in custom_db_command.aliases:
                    custom_db_command.aliases.remove(alias)
                    msg = f'The alias `{alias}` has been removed from `{command}`.'
                else:
                    custom_db_command.aliases = custom_db_command.aliases + [alias]
                    msg = f'The alias `{alias}` has been added to `{command}`.'
            else:
                custom_db_command.aliases = [alias]
                msg = f'The alias `{alias}` has been added to `{command}`.'

            await session.commit()

            await ctx.send(msg)

            if not cmd:
                self.bot.remove_command(custom_command.name)
                custom_command.aliases = await self.get_aliases()
                self.bot.add_command(custom_command)

async def setup(bot: Bot) -> None:
    await bot.add_cog(CustomCommands(bot))
