from contextlib import asynccontextmanager
from asyncpg import TooManyConnectionsError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession, async_sessionmaker, AsyncAttrs
from sqlalchemy import PrimaryKeyConstraint, ForeignKey
from sqlalchemy import BigInteger, Integer, String, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ARRAY, JSON, TIMESTAMP
from typing import Any, AsyncGenerator, Callable, Optional, Coroutine
from datetime import datetime
from sqlalchemy.exc import TimeoutError

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__: str = 'users'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rsn: Mapped[Optional[str]] = mapped_column(String)
    osrs_rsn: Mapped[Optional[str]] = mapped_column(String)
    timezone: Mapped[Optional[str]] = mapped_column(String)

class Guild(Base):
    __tablename__: str = 'guilds'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    prefix: Mapped[Optional[str]] = mapped_column(String)
    welcome_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    welcome_message: Mapped[Optional[str]] = mapped_column(String)
    rs3_news_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    osrs_news_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    log_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    notification_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    role_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    disabled_commands: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    log_bots: Mapped[Optional[bool]] = mapped_column(Boolean)
    modmail_public: Mapped[Optional[int]] = mapped_column(BigInteger)
    modmail_private: Mapped[Optional[int]] = mapped_column(BigInteger)
    hall_of_fame_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger) # deprecated
    hall_of_fame_react_num: Mapped[Optional[int]] = mapped_column(BigInteger)
    bank_role_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    wom_role_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    wom_group_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    wom_verification_code: Mapped[Optional[str]] = mapped_column(String)
    wom_excluded_metrics: Mapped[Optional[str]] = mapped_column(String)
    custom_role_reaction_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    role_reaction_management_role_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    custom_role_reaction_message: Mapped[Optional[str]] = mapped_column(String)

class Role(Base):
    __tablename__: str = 'roles'
    __table_args__ = (
        PrimaryKeyConstraint('guild_id', 'name', name='role_pkey'),
    )
    guild_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String)
    role_id: Mapped[int] = mapped_column(BigInteger)

class Mute(Base):
    __tablename__: str = 'mutes'
    __table_args__ = (
        PrimaryKeyConstraint('guild_id', 'user_id', name='mute_pkey'),
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger)
    expiration: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    reason: Mapped[str] = mapped_column(String)

class Command(Base):
    __tablename__: str = 'commands'
    __table_args__ = (
        PrimaryKeyConstraint('guild_id', 'name', name='command_pkey'),
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    name: Mapped[str] = mapped_column(String)
    function: Mapped[str] = mapped_column(String)
    aliases: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    description: Mapped[Optional[str]] = mapped_column(String)

class Repository(Base):
    __tablename__: str = 'repositories'
    __table_args__ = (
        PrimaryKeyConstraint('guild_id', 'user_name', 'repo_name', name='repo_pkey'),
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    user_name: Mapped[str] = mapped_column(String)
    repo_name: Mapped[str] = mapped_column(String)
    sha: Mapped[str] = mapped_column(String)

class Notification(Base):
    __tablename__: str = 'notifications'
    __table_args__ = (
        PrimaryKeyConstraint('guild_id', 'notification_id', name='notification_pkey'),
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    notification_id: Mapped[int] = mapped_column(Integer)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    interval: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(String)

class OnlineNotification(Base):
    __tablename__: str = 'online_notifications'
    __table_args__ = (
        PrimaryKeyConstraint('guild_id', 'author_id', 'member_id', name='online_notification_pkey'),
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    author_id: Mapped[int] = mapped_column(BigInteger)
    member_id: Mapped[int] = mapped_column(BigInteger)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[int] = mapped_column(Integer)

class Poll(Base):
    __tablename__: str = 'polls'
    __table_args__ = (
        PrimaryKeyConstraint('guild_id', 'message_id', name='poll_pkey'),
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    author_id: Mapped[int] = mapped_column(BigInteger)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    end_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))  

class NewsPost(Base):
    __tablename__: str = 'news_posts'
    link: Mapped[str] = mapped_column(String, primary_key=True)
    game: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    category: Mapped[str] = mapped_column(String)
    image_url: Mapped[str] = mapped_column(String)

class Uptime(Base):
    __tablename__: str = 'uptime'
    time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    status: Mapped[str] = mapped_column(String)

class RS3Item(Base):
    __tablename__: str = 'rs3_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    icon_url: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    members: Mapped[bool] = mapped_column(Boolean)
    current: Mapped[str] = mapped_column(String)
    today: Mapped[str] = mapped_column(String)
    day30: Mapped[str] = mapped_column(String)
    day90: Mapped[str] = mapped_column(String)
    day180: Mapped[str] = mapped_column(String)
    graph_data: Mapped[dict] = mapped_column(JSON)

class OSRSItem(Base):
    __tablename__: str = 'osrs_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    icon_url: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    members: Mapped[bool] = mapped_column(Boolean)
    current: Mapped[str] = mapped_column(String)
    today: Mapped[str] = mapped_column(String)
    day30: Mapped[str] = mapped_column(String)
    day90: Mapped[str] = mapped_column(String)
    day180: Mapped[str] = mapped_column(String)
    graph_data: Mapped[dict] = mapped_column(JSON)

class ClanBankTransaction(Base):
    __tablename__: str = 'clan_bank_transactions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    member_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String)

class CustomRoleReaction(Base):
    __tablename__: str = 'custom_role_reactions'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    emoji_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

class BannedGuild(Base):
    __tablename__: str = 'banned_guilds'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)

class StickyMessage(Base):
    __tablename__: str = 'sticky_messages'
    __table_args__ = (
        PrimaryKeyConstraint('guild_id', 'channel_id', name='sticky_pkey'),
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('guilds.id'), nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger)

class Database():
    config: dict[str, Any]
    restart: Callable[[str | None], Coroutine]

    engine: AsyncEngine
    async_session: async_sessionmaker[AsyncSession]

    def __init__(self, config: dict[str, Any], restart: Callable[[str | None], Coroutine]) -> None:
        self.config = config
        self.restart = restart

        self.engine = self.__get_db_engine()
        self.async_session = self.__get_db_session_maker()

    def __get_db_engine(self) -> AsyncEngine:
        '''
        Get AsyncEngine to connect with the database

        Args:
            config (dict[str, Any]): The config containing the relevant parts of the connection string

        Returns:
            AsyncEngine: The async engine
        '''
        connection_string: str = (f'postgresql+asyncpg://{self.config["postgres_username"]}:{self.config["postgres_password"]}'
            + f'@{self.config["postgres_ip"]}:{self.config["postgres_port"]}/{self.config["postgres_db_name"]}')
        return create_async_engine(connection_string, pool_size=100, max_overflow=90)

    def __get_db_session_maker(self) -> async_sessionmaker[AsyncSession]:
        '''
        Get async session maker to create db sessions

        Returns:
            async_sessionmaker[AsyncSession]: The async session maker
        '''
        # async_sessionmaker: a factory for new AsyncSession objects.
        # expire_on_commit - don't expire objects after transaction commit
        return async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all_database_tables(self) -> None:
        '''
        Creates all database tables.
        '''
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close_connection(self) -> None:
        '''
        Close the database connection by disposing the engine.
        '''
        await self.engine.dispose()

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        '''
        Gets a managed database session.
        The session is automatically closed after it has been used.

        Returns:
            AsyncGenerator[AsyncSession]: AsyncGenerator to generate the AsyncSession

        Yields:
            Iterator[AsyncGenerator[AsyncSession]]: AsyncSession
        '''
        session: AsyncSession | None = None
        try:
            async with self.async_session() as session:
                yield session
        except (TimeoutError, TooManyConnectionsError) as e:
            # In case of unexpected database connection errors, restart the bot.
            # TimeoutError can be caused by a timeout due to hitting the QueuePool limit.
            # TooManyConnectionsError occurs when we exceed the total number of connections allowed by the database.
            # Currently unclear what is causing these issues to occur.
            await self.restart('Restarting after TimeoutError or TooManyConnectionsError...')
        except:
            if session:
                await session.rollback()
            raise
        finally:
            if session:
                await session.close()