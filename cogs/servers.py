import discord
from discord.ext.commands import Cog
import sys
sys.path.append('../')
from bot import Bot, Guild, BannedGuild
from sqlalchemy import select

class Servers(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_guild_join(self, guild):
        async with self.bot.async_session() as session:
            banned_guild = (await session.execute(select(BannedGuild).where(Guild.id == guild.id))).scalar_one_or_none()
            if banned_guild:
                await guild.leave()
                return
            session.add(Guild(id=guild.id, prefix='-'))
            await session.commit()

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.guild.Guild):
        async with self.bot.async_session() as session:
            db_guild = (await session.execute(select(Guild).where(Guild.id == guild.id))).scalar_one_or_none()
            if db_guild:
                await self.bot.purge_guild(db_guild)

async def setup(bot: Bot):
    await bot.add_cog(Servers(bot))
