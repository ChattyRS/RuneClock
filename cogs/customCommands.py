import discord
from discord.ext import commands
from discord.ext.commands import AutoShardedBot as DiscordBot, Cog, CommandError, Context,
import sys
sys.path.append('../')
from main import Bot, config_load, increment_command_counter, Command
import re
import utils
from utils import is_admin

config = config_load()

async def get_aliases():
    aliases = []
    custom_commands = await Command.query.gino.all()
    for command in [c for c in custom_commands if c]:
        if not command.name in aliases:
            aliases.append(command.name)
        if command.aliases:
            for alias in command.aliases:
                if not alias in aliases:
                    aliases.append(alias)
    return aliases

class CustomCommands(Cog):
    bot: Bot

    def __init__(self, bot: Bot):
        self.bot = bot
        self.bot.loop.create_task(self.refresh_custom_command_aliases())
    
    async def refresh_custom_command_aliases(self):
        custom_command = DiscordBot.get_command(self.bot, 'custom_command')
        if custom_command:
            DiscordBot.remove_command(self.bot, 'custom_command')
            custom_command.aliases = await get_aliases()
            DiscordBot.add_command(self.bot, custom_command)

    @commands.command()
    @is_admin()
    async def custom(self, ctx: Context):
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
        increment_command_counter()

        command = ctx.message.clean_content[ctx.message.clean_content.index(' ')+1:].strip()
        if ''.join(command.split()) == command:
            custom_command = await Command.query.where(Command.guild_id==ctx.guild.id).where(Command.name==command).gino.first()
            if custom_command:
                await custom_command.delete()
                custom_command = DiscordBot.get_command(self.bot, 'custom_command')
                DiscordBot.remove_command(self.bot, 'custom_command')
                custom_command.aliases = await get_aliases()
                DiscordBot.add_command(self.bot, custom_command)
                await ctx.send(f'Command `{command}` has been removed.')
                return
            raise CommandError(message=f'Please specify what your command should do. See `help custom`.')
        else:
            name = command.split()[0].lower()
            command = command.replace(name, '', 1).strip()

        cmd = DiscordBot.get_command(self.bot, name)
        custom_command = DiscordBot.get_command(self.bot, 'custom_command')
        if cmd and cmd != custom_command:
            raise CommandError(message=f'Command name `{name}` is already taken, please choose a different one.')
        
        custom_command = await Command.query.where(Command.guild_id==ctx.guild.id).where(Command.name==name).gino.first()
        if custom_command:
            edit = True
            await custom_command.update(function=command).apply()
        else:
            edit = False
            new_custom_command = await Command.create(guild_id=ctx.guild.id, name=name, function=command, aliases=None, description='N/A')

        if not cmd: # alias didn't exist yet, so we need to add it
            custom_command = DiscordBot.get_command(self.bot, 'custom_command')
            DiscordBot.remove_command(self.bot, 'custom_command')
            custom_command.aliases = await get_aliases()
            DiscordBot.add_command(self.bot, custom_command)

        if edit:
            await ctx.send(f'Edited command `{name}` to:\n```{command}```')
        else:
            await ctx.send(f'Added command `{name}`:\n```{command}```')


    @commands.command(hidden=True)
    async def custom_command(self, ctx: commands.Context, *args):
        '''
        Internal function used to call custom commands.
        Do not call this command directly.
        '''
        if not ctx.invoked_with:
            raise CommandError(message=f'Could not find the alias that was used to invoke the command. This is unexpected.')
        alias = ctx.invoked_with.lower()
        custom_command = await Command.query.where(Command.guild_id==ctx.guild.id).where(Command.name==alias).gino.first()
        if not custom_command:
            custom_commands = await Command.query.where(Command.guild_id==ctx.guild.id).gino.all()
            if custom_commands:
                for command in custom_commands:
                    if command.aliases:
                        if alias in command.aliases:
                            custom_command = command
                            break
            if not custom_command:
                return
        
        command = custom_command.function

        increment_command_counter()

        # {require:RoleName} makes this custom command only usable by members who have a role with the given name
        while '{require:' in command:
            begin = command.index('{require:')
            end = command.find('}', begin)
            if end == -1:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            input = command[begin+9:end]
            role_name = input.strip()
            role = discord.utils.find(lambda r: r.name == role_name, ctx.guild.roles)
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
            to_replace = []
            indices = [m.start() for m in re.finditer('\$', command)]
            for index in indices:
                end = min(command.find(' ', index), command.find('}', index))
                if end == -1:
                    end = len(command)
                number = command[index+1:end].replace('}', '')
                if not number:
                    continue
                plus = False
                if '+' in number:
                    plus = True
                    number = number.replace('+', '')
                if not utils.is_int(number):
                    continue
                number = int(number)
                if not plus:
                    try:
                        arg = args[number]
                        to_replace.append(['$' + str(number), arg])
                        continue
                    except:
                        raise CommandError(message=f'Error: required arguments missing. Use `help {alias}`.')
                else:
                    arguments = []
                    for i, arg in enumerate(args):
                        if i >= number:
                            arguments.append(arg)
                    if not arguments and number != 0:
                        raise CommandError(message=f'Error: required arguments missing. Use `help {alias}`.')
                    arg_string = ''
                    for arg in arguments:
                        arg_string += arg + ' '
                    arg_string = arg_string.strip()
                    to_replace.append(['$' + str(number) + '+', arg_string])
                    continue
            if to_replace:
                for tuple in to_replace:
                    old = tuple[0]
                    new = tuple[1]
                    command = command.replace(old, new)

        # {@user} will mention a user by their username (not nickname)
        while '{@' in command:
            begin = command.index('{@')
            end = command.find('}', begin)
            if end == -1:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            input = command[begin+2:end]
            user_name = input.strip()
            member = discord.utils.find(lambda m: m.name == user_name, ctx.guild.members)
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
            channelName = input.strip()
            channel = discord.utils.find(lambda c: str(c.id) == channelName, ctx.guild.channels)
            if not channel:
                channel = discord.utils.find(lambda c: c.name == channelName, ctx.guild.channels)
            if not channel:
                raise CommandError(message=f'Missing channel: `{channelName}`.')
            command = command.replace('{#' + input + '}', channel.mention)

        # {!command} calls a built-in bot command (no custom commands)
        while '{!' in command:
            begin = command.index('{!')
            end = command.find('}', begin)
            if end == -1:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            command_string = command[begin+2:end]
            command = command.replace('{!' + command_string + '}', '')
            space = command_string.find(' ')
            if space == -1:
                space = len(command_string)
            commandName = command_string[:space]
            if commandName == 'customCommand':
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            command_arguments = command_string[space:]
            cmd = self.bot.get_command(commandName)
            if not cmd:
                raise CommandError(message=f'Missing command: `{commandName}`.')
            customCommand = DiscordBot.get_command(self.bot, 'customCommand')
            if cmd == customCommand:
                raise CommandError(message=f'Invalid custom command syntax: `{alias}`.')
            arguments = command_arguments.split()
            try:
                for check in cmd.checks:
                    if not await check(ctx):
                        raise CommandError(message='Error: `Insufficient permissions`.')
                await cmd.callback(self, ctx, *arguments)
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
    async def _commands(self, ctx: commands.Context):
        '''
        Returns list of custom commands.
        '''
        increment_command_counter()

        embed = discord.Embed(title='Commands')
        custom_commands = await Command.query.where(Command.guild_id==ctx.guild.id).gino.all()

        if not custom_commands:
            raise CommandError(message=f'This server does not have any custom commands.')
    
        for command in custom_commands:
            name = command.name
            function, aliases, description = command.function, command.aliases, command.description
            txt = ''
            if aliases:
                txt += 'Aliases: '
                for i, alias in enumerate(aliases):
                    txt += f'`{alias}`'
                    if i < len(aliases)-1:
                        txt += ' | '
            if len(function) <= 40:
                txt += f'\n`{function}`'
            else:
                txt += f'\n`{function[:20]}...`'
            if description:
                if not description == 'N/A':
                    if len(description) <= 80:
                        txt += f'\n{description}'
                    else:
                        txt += f'\n{description[:50]}...'
            if len(embed.fields) < 25:
                embed.add_field(name=name, value=txt, inline=False)
            else:
                try:
                    await ctx.send(embed=embed)
                except:
                    raise CommandError(message=f'Error: `character limit exceeded`.')
                embed.clear_fields()
                embed.add_field(name=name, value=txt, inline=False)

        try:
            await ctx.send(embed=embed)
        except:
            raise CommandError(message=f'Error: `character limit exceeded`.')

    @commands.command(aliases=['description'])
    @is_admin()
    async def describe(self, ctx: commands.Context, command='', *description):
        '''
        Add a short description to a custom command (Admin+).
        '''
        increment_command_counter()

        if not command or not description:
            raise CommandError(message=f'Error: `required arguments missing`')
        
        description = ' '.join(description)

        custom_command = await Command.query.where(Command.guild_id==ctx.guild.id).where(Command.name==command).gino.first()
        if not custom_command:
            raise CommandError(message=f'Error: no such command: `{command}`.')

        await custom_command.update(description=description).apply()

        await ctx.send(f'Your discription has been added to `{command}`.')

    @commands.command(name='alias')
    @is_admin()
    async def _alias(self, ctx: commands.Context, command='', alias=''):
        '''
        Add/remove an alias for a custom command (Admin+).
        '''
        increment_command_counter()

        if not command or not alias:
            raise CommandError(message=f'Error: `required arguments missing`.')

        cmd = DiscordBot.get_command(self.bot, alias)
        custom_command = DiscordBot.get_command(self.bot, 'custom_command')
        if cmd and cmd != custom_command:
            raise CommandError(message=f'Error: `alias already in use`.')
        
        msg = ''
        custom_command = await Command.query.where(Command.guild_id==ctx.guild.id).where(Command.name==command).gino.first()
        if not custom_command:
            raise CommandError(message=f'Error: no such command: `{command}`.')

        if custom_command.aliases:
            if alias in custom_command.aliases:
                await custom_command.update(aliases = custom_command.aliases.remove(alias)).apply()
                msg = f'The alias `{alias}` has been removed from `{command}`.'
            else:
                await custom_command.update(aliases=custom_command.aliases + [alias]).apply()
                msg = f'The alias `{alias}` has been added to `{command}`.'
        else:
            await custom_command.update(aliases=[alias]).apply()
            msg = f'The alias `{alias}` has been added to `{command}`.'
        await ctx.send(msg)

        if not cmd:
            custom_command = DiscordBot.get_command(self.bot, 'custom_command')
            DiscordBot.remove_command(self.bot, 'custom_command')
            custom_command.aliases = await get_aliases()
            DiscordBot.add_command(self.bot, custom_command)

async def setup(bot: Bot):
    await bot.add_cog(CustomCommands(bot))
