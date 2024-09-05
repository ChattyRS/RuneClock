from bot import Bot
from discord import Guild, Role, TextChannel, Thread
from discord.guild import GuildChannel
from discord.abc import PrivateChannel
from discord.ext.commands import Command, CommandError

def find_guild_text_channel(guild: Guild, id: int | None) -> TextChannel | None:
    '''
    Finds a text channel in a guild.

    Args:
        guild (Guild): The guild
        id (int | None): The channel id

    Returns:
        TextChannel | None: The channel if found
    '''
    channel: GuildChannel | None = guild.get_channel(id) if id else None
    return channel if isinstance(channel, TextChannel) else None

def get_guild_text_channel(guild: Guild, id: int | None) -> TextChannel:
    '''
    Gets a text channel in a guild

    Args:
        guild (Guild): The guild
        id (int | None): The channel id

    Raises:
        Exception: If the channel is not found

    Returns:
        TextChannel: The channel
    '''
    channel: TextChannel | None = find_guild_text_channel(guild, id)
    if not channel:
        raise Exception(f'Guild channel with id {id if id else "None"} was not found.')
    return channel

def find_text_channel(bot: Bot, id: int | None) -> TextChannel | None:
    '''
    Finds a text channel

    Args:
        bot (Bot): The bot
        id (int | None): The channel id

    Returns:
        TextChannel | None: The channel if found
    '''
    channel: GuildChannel | Thread | PrivateChannel | None = bot.get_channel(id) if id else None
    return channel if isinstance(channel, TextChannel) else None

def get_text_channel(bot: Bot, id: int | None) -> TextChannel:
    '''
    Gets a text channel

    Args:
        bot (Bot): The bot
        id (int | None): The channel id

    Raises:
        Exception: If the channel is not found

    Returns:
        TextChannel: The channel
    '''
    channel: TextChannel | None = find_text_channel(bot, id)
    if not channel:
        raise Exception(f'Channel with id {id if id else "None"} was not found.')
    return channel

def find_role(bot: Bot, guild_or_id: Guild | int | None, role_id: int | None) -> Role | None:
    '''
    Finds a role

    Args:
        bot (Bot): The bot
        guild_or_id (Guild | int | None): The guild or id
        role_id (int | None): The role id

    Raises:
        Exception: If the guild is not found

    Returns:
        Role | None: The role
    '''
    guild: Guild | None = guild_or_id if isinstance(guild_or_id, Guild) else None
    if not guild and isinstance(guild_or_id, int):
        guild = bot.get_guild(guild_or_id)
    if not guild:
        raise Exception(f'Guild with id {guild_or_id if guild_or_id else "None"} was not found.')
    role: Role | None = guild.get_role(role_id) if role_id else None
    return role

def get_role(bot: Bot, guild_or_id: Guild | int | None, role_id: int | None) -> Role:
    '''
    Gets a role

    Args:
        bot (Bot): The bot
        guild_or_id (Guild | int | None): The guild or id
        role_id (int | None): The role id

    Raises:
        Exception: If the role is not found

    Returns:
        Role: The role
    '''
    role: Role | None = find_role(bot, guild_or_id, role_id)
    if not role:
        raise Exception(f'Role with id {role_id if role_id else "None"} was not found.')
    return role

def get_custom_command(bot: Bot, command_name: str | None = None) -> Command:
    '''
    Gets a custom command by name.
    If no name is provided, the template "custom_command" will be returned.

    Args:
        command_name (str | None, optional): Command name. Defaults to None.

    Raises:
        CommandError: If the command is not found.

    Returns:
        Command: The command.
    '''
    command_name = command_name if command_name else 'custom_command' # Default built in 'custom_command', used as a proxy to execute custom commands
    custom_command: Command | None = bot.get_command(command_name)
    if not custom_command:
        raise CommandError(message=f'Custom command `{command_name}` was not found.')
    return custom_command