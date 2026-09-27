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
        db_guild: Guild | None = None
        async with self.bot.db.get_session() as session:
            banned_guild: BannedGuild | None = (await session.execute(select(BannedGuild).where(Guild.id == guild.id))).scalar_one_or_none()
            if not banned_guild:
                db_guild = Guild(id=guild.id, prefix='-')
                session.add(db_guild)
                await session.commit()
                self.bot.cache.guild(db_guild)
        if banned_guild:
            await guild.leave()
            return

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        '''
        When the bot is removed from a guild, purge any data relating to that guild from the database.

        Args:
            guild (discord.Guild): The guild that the bot was removed from.
        '''
        db_guild: Guild | None = self.bot.cache.get_guild(guild)
        if db_guild:
            async with self.bot.db.get_session() as session:
                await purge_guild(session, db_guild)
                await session.commit()
        # Remove guild from cache
        if self.bot.cache.get_guild(guild):
            del self.bot.cache.guilds[guild.id]

async def setup(bot: Bot) -> None:
    await bot.add_cog(Servers(bot))
