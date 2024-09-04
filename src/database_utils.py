from bot import Bot
from discord import Guild as DiscordGuild
from database import Guild
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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