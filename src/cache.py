from typing import Sequence
import discord
from sqlalchemy import select
from src.database import Database, Guild, OSRSItem, RS3Item, User, OnlineNotification, StickyMessage

class Cache():
    db: Database

    guilds: dict[int, Guild] = {} # id -> Guild
    users: dict[int, User] = {} # id -> User
    osrs_items: dict[int, OSRSItem] = {} # id -> OSRSItem
    rs3_items: dict[int, RS3Item] = {} # id -> RS3Item
    online_notifications: dict[tuple[int, int], dict[int, OnlineNotification]] = {} # (guild_id, member_id) -> {author_id: OnlineNotification}
    sticky_messages: dict[int, StickyMessage] = {} # channel_id -> StickyMessage

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
        - OnlineNotification
        - StickyMessage
        '''
        await self.__cache_guilds()
        await self.__cache_users()
        await self.__cache_items_osrs()
        await self.__cache_items_rs3()
        await self.__cache_online_notifications()
        await self.__cache_sticky_messages()

    async def __cache_guilds(self) -> None:
        '''
        Initialize guild cache
        This is used to keep track of guild prefixes without needing to perform database requests for each message
        '''
        guilds: Sequence[Guild] = []
        async with self.db.get_session() as session:
            guilds = (await session.execute(select(Guild))).scalars().all()
        for g in guilds:
            self.guilds[g.id] = g

    async def __cache_users(self) -> None:
        '''
        Initialize user cache
        This is used to keep track of user preferences without needing to perform database requests for each message
        '''
        users: Sequence[User] = []
        async with self.db.get_session() as session:
            users = (await session.execute(select(User))).scalars().all()
        for u in users:
            self.users[u.id] = u

    async def __cache_items_osrs(self) -> None:
        '''
        Initialize OSRS item cache
        '''
        items: Sequence[OSRSItem] = []
        async with self.db.get_session() as session:
            items = (await session.execute(select(OSRSItem))).scalars().all()
        for i in items:
            self.osrs_items[i.id] = i
    
    async def __cache_items_rs3(self) -> None:
        '''
        Initialize RS3 item cache
        '''
        items: Sequence[RS3Item] = []
        async with self.db.get_session() as session:
            items = (await session.execute(select(RS3Item))).scalars().all()
        for i in items:
            self.rs3_items[i.id] = i

    async def __cache_online_notifications(self) -> None:
        '''
        Initialize online notification cache
        '''
        notifications: Sequence[OnlineNotification] = []
        async with self.db.get_session() as session:
            notifications = (await session.execute(select(OnlineNotification))).scalars().all()
        self.online_notifications = {}
        for n in notifications:
            self.online_notification(n)

    async def __cache_sticky_messages(self) -> None:
        '''
        Initialize sticky message cache
        '''
        sticky_messages: Sequence[StickyMessage] = []
        async with self.db.get_session() as session:
            sticky_messages = (await session.execute(select(StickyMessage))).scalars().all()
        for m in sticky_messages:
            self.sticky_messages[m.channel_id] = m

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

    def get_online_notifications(self, guild_id: int, member_id: int) -> list[OnlineNotification]:
        '''
        Get all cached online notifications tracking a given member in a given guild.

        Args:
            guild_id (int): The guild id
            member_id (int): The id of the member being tracked

        Returns:
            list[OnlineNotification]: The online notifications, if any.
        '''
        return list(self.online_notifications.get((guild_id, member_id), {}).values())

    def get_online_notification(self, guild_id: int, member_id: int, author_id: int) -> OnlineNotification | None:
        '''
        Get a single cached online notification by its primary key.

        Args:
            guild_id (int): The guild id
            member_id (int): The id of the member being tracked
            author_id (int): The id of the user who requested the notification

        Returns:
            OnlineNotification | None: The online notification, if found.
        '''
        return self.online_notifications.get((guild_id, member_id), {}).get(author_id)

    def online_notification(self, notification: OnlineNotification) -> None:
        '''
        Add / update an online notification in the cache.

        Args:
            notification (OnlineNotification): The online notification
        '''
        self.online_notifications.setdefault((notification.guild_id, notification.member_id), {})[notification.author_id] = notification

    def remove_online_notification(self, notification: OnlineNotification) -> None:
        '''
        Remove an online notification from the cache.

        Args:
            notification (OnlineNotification): The online notification
        '''
        key: tuple[int, int] = (notification.guild_id, notification.member_id)
        by_author: dict[int, OnlineNotification] | None = self.online_notifications.get(key)
        if by_author is None:
            return
        by_author.pop(notification.author_id, None)
        if not by_author:
            del self.online_notifications[key]

    def get_sticky_message(self, channel_id: int) -> StickyMessage | None:
        '''
        Get the cached sticky message for a channel.

        Args:
            channel_id (int): The channel id

        Returns:
            StickyMessage | None: The sticky message, if any.
        '''
        return self.sticky_messages.get(channel_id)

    def sticky_message(self, sticky_message: StickyMessage) -> None:
        '''
        Add / update a sticky message in the cache.

        Args:
            sticky_message (StickyMessage): The sticky message
        '''
        self.sticky_messages[sticky_message.channel_id] = sticky_message

    def remove_sticky_message(self, channel_id: int) -> None:
        '''
        Remove the sticky message for a channel from the cache.

        Args:
            channel_id (int): The channel id
        '''
        self.sticky_messages.pop(channel_id, None)

    def purge_guild(self, guild_id: int) -> None:
        '''
        Remove all cached data for a guild. Call this after purging the guild from the database.

        Args:
            guild_id (int): The guild id
        '''
        self.guilds.pop(guild_id, None)
        for key in [k for k in self.online_notifications if k[0] == guild_id]:
            del self.online_notifications[key]
        for channel_id in [c for c, s in self.sticky_messages.items() if s.guild_id == guild_id]:
            del self.sticky_messages[channel_id]