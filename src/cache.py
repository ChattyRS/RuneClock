from typing import Sequence
import discord
from sqlalchemy import select
from src.database import Database, Guild, OSRSItem, RS3Item, User

class Cache():
    db: Database

    guilds: dict[int, Guild] = {}
    users: dict[int, User] = {}
    osrs_items: dict[int, OSRSItem] = {}
    rs3_items: dict[int, RS3Item] = {}

    def __init__(self, db: Database) -> None:
        self.db = db

    async def build(self) -> None:
        '''
        Builds caches for the bot from data stored in the database.
        Currently caching:
        - Guild
        - User
        - OSRSItem
        - RS3Item
        '''
        await self.__cache_guilds()
        await self.__cache_users()
        await self.__cache_items_osrs()
        await self.__cache_items_rs3()

    async def __cache_guilds(self) -> None:
        '''
        Initialize guild cache
        This is used to keep track of guild prefixes without needing to perform database requests for each message
        '''
        guilds: Sequence[Guild] = []
        async with self.db.get_session() as session:
            guilds: Sequence[Guild] = (await session.execute(select(Guild))).scalars().all()
        for g in guilds:
            self.guilds[g.id] = g

    async def __cache_users(self) -> None:
        '''
        Initialize user cache
        This is used to keep track of user preferences without needing to perform database requests for each message
        '''
        users: Sequence[User] = []
        async with self.db.get_session() as session:
            users: Sequence[User] = (await session.execute(select(User))).scalars().all()
        for u in users:
            self.users[u.id] = u

    async def __cache_items_osrs(self) -> None:
        '''
        Initialize OSRS item cache
        '''
        items: Sequence[OSRSItem] = []
        async with self.db.get_session() as session:
            items: Sequence[OSRSItem] = (await session.execute(select(OSRSItem))).scalars().all()
        for i in items:
            self.osrs_items[i.id] = i
    
    async def __cache_items_rs3(self) -> None:
        '''
        Initialize RS3 item cache
        '''
        items: Sequence[RS3Item] = []
        async with self.db.get_session() as session:
            items: Sequence[RS3Item] = (await session.execute(select(RS3Item))).scalars().all()
        for i in items:
            self.rs3_items[i.id] = i

    def get_guild(self, guild_or_id: discord.Guild | int | None) -> Guild | None:
        '''
        Get a db guild from the cache.

        Args:
            guild_id (int): The guild id

        Returns:
            Guild | None: The guild, if found.
        '''
        guild_id: int | None = guild_or_id.id if isinstance(guild_or_id, discord.Guild) else guild_or_id
        return self.guilds[guild_id] if guild_id and guild_id in self.guilds else None
    
    def guild(self, guild: Guild) -> None:
        '''
        Add / update a db guild to the cache.

        Args:
            guild (Guild): The guild to add to the cache.
        '''
        self.guilds[guild.id] = guild

    def get_user(self, user_or_id: discord.User | discord.Member | int | None) -> User | None:
        '''
        Get a db user from the cache.

        Args:
            user_or_id (int): The user or user id

        Returns:
            User | None: The user, if found.
        '''
        user_id: int | None = user_or_id.id if isinstance(user_or_id, discord.User) or isinstance(user_or_id, discord.Member) else user_or_id
        return self.users[user_id] if user_id and user_id in self.users else None
    
    def user(self, user: User) -> None:
        '''
        Add / update a db user to the cache.

        Args:
            user (Guild): The user to add to the cache.
        '''
        self.users[user.id] = user

    def get_osrs_items_by_name(self, name: str) -> list[OSRSItem]:
        '''
        Get a list of OSRS items from cache where the name contains the given input.
        Results are sorted by the accuracy of the match.

        Args:
            name (str): The item name to search for

        Returns:
            list[OSRSItem]: OSRS items sorted by match accuracy.
        '''
        matching_items: list[OSRSItem] = [item for item in self.osrs_items.values() if name.lower() in item.name.lower()]
        if not matching_items:
            return []
        # Get the best matches by sorting the item with the shortest name: i.e. the one closest to the provided input
        # We apply a further preference to item names which start with the given input, by doubling the sort priority of any other items.
        sorted_matches: list[OSRSItem] = sorted(matching_items, key=lambda i: len(i.name) if i.name.lower().startswith(name.lower()) else 2*len(i.name))
        return sorted_matches

    def get_osrs_item_by_name(self, name: str) -> OSRSItem | None:
        '''
        Get OSRS item from cache with name closest to the given input, if any.

        Args:
            name (str): The substring of item name to search for

        Returns:
            OSRSItem | None: Best matching OSRS item, if any
        '''
        # Get the best match by picking the item with the shortest name: i.e. the one closest to the provided input
        sorted_matches: list[OSRSItem] = self.get_osrs_items_by_name(name)
        return sorted_matches[0] if len(sorted_matches) > 0 else None
    
    def get_rs3_item_by_name(self, name: str) -> RS3Item | None:
        '''
        Get RS3 item from cache with name closest to the given input, if any.

        Args:
            name (str): The substring of item name to search for

        Returns:
            RS3Item | None: Best matching RS3 item, if any
        '''
        matching_items: list[RS3Item] = [item for item in self.rs3_items.values() if name.lower() in item.name.lower()]
        if not matching_items:
            return None
        # Get the best match by picking the item with the shortest name: i.e. the one closest to the provided input
        sorted_matches: list[RS3Item] = sorted(matching_items, key=lambda i: len(i.name))
        return sorted_matches[0]