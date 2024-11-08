from typing import Sequence
from discord import Guild as DiscordGuild
from src.database import ClanBankTransaction, CustomRoleReaction, Guild, Command, Mute, Notification, OSRSItem, OnlineNotification, Poll, RS3Item, Repository, Role
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from discord.ext.commands import CommandError

async def find_db_guild(session: AsyncSession, guild_or_id: DiscordGuild | int | None) -> Guild | None:
    '''
    Finds a database Guild.

    Args:
        session (Bot): The async session
        guild_or_id (DiscordGuild | int | None): The discord Guild or id

    Returns:
        Guild | None: The database Guild if found
    '''
    id: int | None = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id
    return (await session.execute(select(Guild).where(Guild.id == id))).scalar_one_or_none()

async def get_db_guild(session: AsyncSession, guild_or_id: DiscordGuild | int | None) -> Guild:
    '''
    Gets a database Guild

    Args:
        session (Bot): The async session
        guild_or_id (DiscordGuild | int | None): The discord Guild or id

    Raises:
        Exception: If guild_or_id is not given
        Exception: If the Guild is not found in the database

    Returns:
        Guild: _description_
    '''
    id: int | None = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id
    if not id:
        raise Exception(f'Attempted to get a guild from the database but ID was None.')
    guild: Guild | None = await find_db_guild(session, id)
    if not guild:
        raise Exception(f'Guild with id {id} was not found.')
    return guild

async def create_db_guild(session: AsyncSession, guild_or_id: DiscordGuild | int) -> Guild:
    '''
    Creates a Guild in the database

    Args:
        session (Bot): The async session
        guild_or_id (DiscordGuild | int): The discord Guild or id

    Returns:
        Guild: The created database Guild
    '''
    id: int = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id
    instance = Guild(id=id, prefix='-')
    session.add(instance)
    await session.commit()
    return instance

async def find_or_create_db_guild(session: AsyncSession, guild_or_id: DiscordGuild | int) -> Guild:
    '''
    Finds or creates a database Guild

    Args:
        session (Bot): The async session
        guild_or_id (DiscordGuild | int): The discord Guild or id

    Returns:
        Guild: The database Guild
    '''
    db_guild: Guild | None = await find_db_guild(session, guild_or_id)
    return db_guild if db_guild else await create_db_guild(session, guild_or_id)

async def find_custom_db_command(session: AsyncSession, guild_or_id: DiscordGuild | int | None, command_name_or_alias: str) -> Command | None:
    '''
    Finds a custom command in the database.

    Args:
        session (Bot): The async session
        guild_or_id (DiscordGuild | int | None): The discord guild or guild id
        command_name_or_alias (str): The command name or an alias

    Returns:
        Command: The command if found.
    '''
    if guild_or_id is None:
        return None
    guild_id: int = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id

    custom_db_commands: Sequence[Command] = (await session.execute(select(Command).where(Command.guild_id == guild_id))).scalars().all()
    for custom_db_command in custom_db_commands:
        if custom_db_command.name == command_name_or_alias:
            return custom_db_command
    for custom_db_command in custom_db_commands:
        if custom_db_command.aliases and command_name_or_alias in custom_db_command.aliases:
            return custom_db_command
    
async def get_custom_db_commands(session: AsyncSession, guild_or_id: DiscordGuild | int | None) -> Sequence[Command]:
    '''
    Gets all custom commands for the given guild from the database.

    Args:
        session (Bot): The async session
        guild_or_id (DiscordGuild | int | None): The discord guild or guild id

    Raises:
        CommandError: If the guild id not found

    Returns:
        Sequence[Command]: The guild's custom commands.
    '''
    if guild_or_id is None:
        raise CommandError(message=f'Cannot use custom commands outside of a server.')
    guild_id: int = guild_or_id.id if isinstance(guild_or_id, DiscordGuild) else guild_or_id
    custom_db_commands: Sequence[Command] = (await session.execute(select(Command).where(Command.guild_id == guild_id))).scalars().all()
    return custom_db_commands
    
async def find_osrs_item_by_id(session: AsyncSession, id: int) -> OSRSItem | None:
    '''
    Finds an OSRS item by id.

    Args:
        session (Bot): The async session
        id (int): The item id

    Returns:
        OSRSItem | None: The OSRS item
    '''
    return (await session.execute(select(OSRSItem).where(OSRSItem.id == id))).scalar_one_or_none()
    
async def get_osrs_item_by_id(session: AsyncSession, id: int) -> OSRSItem:
    '''
    Gets an OSRS item by id.

    Args:
        session (Bot): The async session
        id (int): The item id

    Raises:
        CommandError: If the item is not found

    Returns:
        OSRSItem: The OSRS item
    '''
    item: OSRSItem | None = await find_osrs_item_by_id(session, id)
    if not item:
        raise CommandError(f'Item with ID {id} was not found.')
    return item

async def find_rs3_item_by_id(session: AsyncSession, id: int) -> RS3Item | None:
    '''
    Finds an RS3 item by id.

    Args:
        session (Bot): The async session
        id (int): The item id

    Returns:
        RS3Item | None: The RS3 item
    '''
    return (await session.execute(select(RS3Item).where(RS3Item.id == id))).scalar_one_or_none()
    
async def get_rs3_item_by_id(session: AsyncSession, id: int) -> RS3Item:
    '''
    Gets an RS3 item by id.

    Args:
        session (Bot): The async session
        id (int): The item id

    Raises:
        CommandError: If the item is not found

    Returns:
        RS3Item: The RS3 item
    '''
    item: RS3Item | None = await find_rs3_item_by_id(session, id)
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

async def get_role_reactions(session: AsyncSession, guild_id: int) -> Sequence[CustomRoleReaction]:
    '''
    Gets all CustomRoleReaction for a given guild.

    Args:
        session (Bot): The async session
        guild_id (int): The guild id

    Returns:
        Sequence[CustomRoleReaction]: The custom role reactions for the guild.
    '''
    return (await session.execute(select(CustomRoleReaction).where(CustomRoleReaction.guild_id == guild_id))).scalars().all()