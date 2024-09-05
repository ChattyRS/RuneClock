from typing import Sequence
from bot import Bot
from discord import Guild as DiscordGuild
from database import Guild, Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from discord.ext.commands import CommandError

async def find_db_guild(bot: Bot, guild_or_id: DiscordGuild | int | None, session: AsyncSession | None = None) -> Guild | None:
    '''
    Finds a database Guild.

    Args:
        bot (Bot): The bot
        guild_or_id (DiscordGuild | int | None): The discord Guild or id
        session (AsyncSession | None, optional): The database session to use (optional). Defaults to None.

    Returns:
        Guild | None: The database Guild if found
    '''
    id: int | None = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id
    if session:
        return (await session.execute(select(Guild).where(Guild.id == id))).scalar_one_or_none()
    async with bot.async_session() as session:
        return (await session.execute(select(Guild).where(Guild.id == id))).scalar_one_or_none()

async def get_db_guild(bot: Bot, guild_or_id: DiscordGuild | int | None, session: AsyncSession | None = None) -> Guild:
    '''
    Gets a database Guild

    Args:
        bot (Bot): The bot
        guild_or_id (DiscordGuild | int | None): The discord Guild or id
        session (AsyncSession | None, optional): The database session to use (optional). Defaults to None.

    Raises:
        Exception: If guild_or_id is not given
        Exception: If the Guild is not found in the database

    Returns:
        Guild: _description_
    '''
    id: int | None = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id
    if not id:
        raise Exception(f'Attempted to get a guild from the database but ID was None.')
    guild: Guild | None = await find_db_guild(bot, id, session)
    if not guild:
        raise Exception(f'Guild with id {id} was not found.')
    return guild

async def create_db_guild(bot: Bot, guild_or_id: DiscordGuild | int) -> Guild:
    '''
    Creates a Guild in the database

    Args:
        bot (Bot): The bot
        guild_or_id (DiscordGuild | int): The discord Guild or id

    Returns:
        Guild: The created database Guild
    '''
    id: int = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id
    async with bot.async_session() as session:
        instance = Guild(id=id, prefix='-')
        session.add(instance)
        await session.commit()
    return instance

async def find_or_create_db_guild(bot: Bot, guild_or_id: DiscordGuild | int) -> Guild:
    '''
    Finds or creates a database Guild

    Args:
        bot (Bot): The bot
        guild_or_id (DiscordGuild | int): The discord Guild or id

    Returns:
        Guild: The database Guild
    '''
    db_guild: Guild | None = await find_db_guild(bot, guild_or_id)
    return db_guild if db_guild else await create_db_guild(bot, guild_or_id)

async def find_custom_db_command(bot: Bot, guild_or_id: DiscordGuild | int | None, command_name_or_alias: str, db_session: AsyncSession | None = None) -> Command | None:
    '''
    Finds a custom command in the database.

    Args:
        bot (Bot): The bot
        guild_or_id (DiscordGuild | int | None): The discord guild or guild id
        command_name_or_alias (str): The command name or an alias
        db_session (AsyncSession | None, optional): The database session. If not provided, a new session will be created. Defaults to None.

    Returns:
        Command: The command if found.
    '''
    if guild_or_id is None:
        return None
    guild_id: int = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id

    async with db_session if db_session else bot.async_session() as session:
        custom_db_command: Command | None = (await session.execute(select(Command).where(Command.guild_id == guild_id).where(or_(Command.name == command_name_or_alias, Command.aliases.contains(command_name_or_alias))))).scalar_one_or_none()
        return custom_db_command
    
async def get_custom_db_commands(bot: Bot, guild_or_id: DiscordGuild | int | None) -> Sequence[Command]:
    '''
    Gets all custom commands for the given guild from the database.

    Args:
        bot (Bot): The bot
        guild_or_id (DiscordGuild | int | None): The discord guild or guild id

    Raises:
        CommandError: If the guild id not found

    Returns:
        Sequence[Command]: The guild's custom commands.
    '''
    if guild_or_id is None:
        raise CommandError(message=f'Cannot use custom commands outside of a server.')
    guild_id: int = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id
    async with bot.async_session() as session:
        custom_db_commands: Sequence[Command] = (await session.execute(select(Command).where(Command.guild_id == guild_id))).scalars().all()
        return custom_db_commands