from discord import Embed, Guild, Permissions, Role, TextChannel, Thread
from discord.abc import GuildChannel, PrivateChannel
from discord.ext.commands import Command, CommandError, Context, AutoShardedBot as Bot

max_message_length: int = 2000
max_embed_description_length: int = 4096
num_emoji: list[str] = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯', '🇰', '🇱', '🇲', '🇳', '🇴', '🇵', '🇶', '🇷', '🇸', '🇹']

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

def find_text_channel_by_name(guild: Guild, channel_name: str) -> TextChannel | None:
    '''
    Finds a guild text channel by name.

    Args:
        guild (Guild): The guild
        channel_name (str): The channel name to search for

    Returns:
        TextChannel | None: The channel
    '''
    return next((c for c in guild.text_channels if c.name.upper() == channel_name.upper()), None)

def get_text_channel_by_name(guild: Guild, channel_name: str) -> TextChannel:
    '''
    Gets a guild text channel by name.

    Args:
        guild (Guild): The guild
        channel_name (str): The channel name to search for

    Raises:
        CommandError: If no such channel is found

    Returns:
        TextChannel: The channel
    '''
    channel: TextChannel | None = next((c for c in guild.text_channels if c.name.upper() == channel_name.upper()), None)
    if not channel:
        raise CommandError(f'Channel not found: {channel_name}')
    return channel

async def send_code_block_over_multiple_messages(ctx: Context, message: str) -> None:
    # https://stackoverflow.com/questions/13673060/split-string-into-strings-by-length
    chunk_size: int = max_message_length - 6 # We have 6 "`"" chars
    characters: int = len(message) # number of chunks is initialized at the length of the message
    message_chunks: list[str] = [message[i:i+chunk_size] for i in range(0, characters, chunk_size)]
    for message_chunk in message_chunks:
        await ctx.send(f'```{message_chunk}```')

async def send_lines_over_multiple_messages(ctx: Context, message: str | list[str]) -> None:
    lines: list[str] = message.split('\n') if isinstance(message, str) else message

    txt: str = ''
    for line in lines:
        if len(txt + line) > max_message_length:
            await ctx.send(txt)
            txt = ''
        txt += line
    if txt:
        await ctx.send(txt)

async def send_lines_over_multiple_embeds(ctx: Context, message: str | list[str], embed: Embed) -> None:
    lines: list[str] = message.split('\n') if isinstance(message, str) else message

    embed.description = ''
    for line in lines:
        if len(embed.description + line) > max_embed_description_length:
            await ctx.send(embed = embed)
            embed.description = ''
        embed.description += '\n' + line if embed.description else line
    if embed.description:
        await ctx.send(embed = embed)

def perm_string(p: Permissions) -> str:
    '''
    Translates permissions to a string of important permissions.

    Args:
        p (_type_): Permissions

    Returns:
        str: String listing various important permissions.
    '''
    s: str = ''

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