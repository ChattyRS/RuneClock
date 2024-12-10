import discord
from discord.ext.commands import Cog
from src.database_utils import purge_guild
from src.bot import Bot
from src.database import Guild, BannedGuild
from sqlalchemy import select

class Servers(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        '''
        When a guild is joined, check that the guild is not banned. Otherwise, add it to the database with the default prefix.

        Args:
            guild (_type_): The guild that was joined
        '''
        async with self.bot.get_session() as session:
            banned_guild: BannedGuild | None = (await session.execute(select(BannedGuild).where(Guild.id == guild.id))).scalar_one_or_none()
            if banned_guild:
                await guild.leave()
                return
            db_guild: Guild = Guild(id=guild.id, prefix='-')
            session.add(db_guild)
            await session.commit()
            # Add guild to the cache
            self.bot.db_guild_cache[guild.id] = db_guild

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        '''
        When the bot is removed from a guild, purge any data relating to that guild from the database.

        Args:
            guild (discord.Guild): The guild that the bot was removed from.
        '''
        async with self.bot.get_session() as session:
            db_guild: Guild | None = (await session.execute(select(Guild).where(Guild.id == guild.id))).scalar_one_or_none()
            if db_guild:
                await purge_guild(session, db_guild)
                await session.commit()
        # Remove guild from cache
        if guild.id in self.bot.db_guild_cache:
            del self.bot.db_guild_cache[guild.id]

async def setup(bot: Bot) -> None:
    await bot.add_cog(Servers(bot))
