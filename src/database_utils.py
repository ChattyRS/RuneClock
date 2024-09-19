from typing import Sequence
from bot import Bot
from discord import Guild as DiscordGuild
from database import ClanBankTransaction, CustomRoleReaction, Guild, Command, Mute, Notification, OSRSItem, OnlineNotification, Poll, RS3Item, Repository, Role
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, or_, select
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
    
async def find_osrs_item_by_id(bot: Bot, id: int, db_session: AsyncSession | None = None) -> OSRSItem | None:
    '''
    Finds an OSRS item by id.

    Args:
        bot (Bot): The bot
        id (int): The item id
        db_session (AsyncSession | None, optional): The database session. Defaults to None.

    Returns:
        OSRSItem | None: The OSRS item
    '''
    async with db_session if db_session else bot.async_session() as session:
        return (await session.execute(select(OSRSItem).where(OSRSItem.id == id))).scalar_one_or_none()
    
async def get_osrs_item_by_id(bot: Bot, id: int, db_session: AsyncSession | None = None) -> OSRSItem:
    '''
    Gets an OSRS item by id.

    Args:
        bot (Bot): The bot
        id (int): The item id
        db_session (AsyncSession | None, optional): The database session. Defaults to None.

    Raises:
        CommandError: If the item is not found

    Returns:
        OSRSItem: The OSRS item
    '''
    item: OSRSItem | None = await find_osrs_item_by_id(bot, id, db_session)
    if not item:
        raise CommandError(f'Item with ID {id} was not found.')
    return item

async def find_rs3_item_by_id(bot: Bot, id: int, db_session: AsyncSession | None = None) -> RS3Item | None:
    '''
    Finds an RS3 item by id.

    Args:
        bot (Bot): The bot
        id (int): The item id
        db_session (AsyncSession | None, optional): The database session. Defaults to None.

    Returns:
        RS3Item | None: The RS3 item
    '''
    async with db_session if db_session else bot.async_session() as session:
        return (await session.execute(select(RS3Item).where(RS3Item.id == id))).scalar_one_or_none()
    
async def get_rs3_item_by_id(bot: Bot, id: int, db_session: AsyncSession | None = None) -> RS3Item:
    '''
    Gets an RS3 item by id.

    Args:
        bot (Bot): The bot
        id (int): The item id
        db_session (AsyncSession | None, optional): The database session. Defaults to None.

    Raises:
        CommandError: If the item is not found

    Returns:
        RS3Item: The RS3 item
    '''
    item: RS3Item | None = await find_rs3_item_by_id(bot, id, db_session)
    if not item:
        raise CommandError(f'Item with ID {id} was not found.')
    return item

async def purge_guild(session: AsyncSession, guild: Guild) -> None:
    '''
    Purge all data relating to a specific Guild from the database

    Args:
        session (AsyncSession): The database session
        guild (Guild): The guild whose data to purge
    '''
    await session.execute(delete(Role).where(Role.guild_id == guild.id))
    await session.execute(delete(Mute).where(Mute.guild_id == guild.id))
    await session.execute(delete(Command).where(Command.guild_id == guild.id))
    await session.execute(delete(Repository).where(Repository.guild_id == guild.id))
    await session.execute(delete(Notification).where(Notification.guild_id == guild.id))
    await session.execute(delete(OnlineNotification).where(OnlineNotification.guild_id == guild.id))
    await session.execute(delete(Poll).where(Poll.guild_id == guild.id))
    await session.execute(delete(ClanBankTransaction).where(ClanBankTransaction.guild_id == guild.id))
    await session.execute(delete(CustomRoleReaction).where(CustomRoleReaction.guild_id == guild.id))
    await session.delete(guild)

async def get_role_reactions(bot: Bot, guild_id: int, db_session: AsyncSession | None = None) -> Sequence[CustomRoleReaction]:
    '''
    Gets all CustomRoleReaction for a given guild.

    Args:
        bot (Bot): The bot
        guild_id (int): The guild id
        db_session (AsyncSession | None, optional): The database session. Defaults to None.

    Returns:
        Sequence[CustomRoleReaction]: The custom role reactions for the guild.
    '''
    async with db_session if db_session else bot.async_session() as session:
        return (await session.execute(select(CustomRoleReaction).where(CustomRoleReaction.guild_id == guild_id))).scalars().all()