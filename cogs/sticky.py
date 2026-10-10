import discord
from discord.ext import commands
from discord.ext.commands import Cog
from sqlalchemy import delete, update
from src.checks import is_admin
from src.bot import Bot
from src.database import StickyMessage

class Sticky(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        '''
        This event triggers on every message received by the bot. Including ones that it sent itself.
        When a message is sent in a text channel with a sticky message, the sticky message will be re-sent.

        Args:
            message (discord.Message): The message
        '''
        # Only process sticky message in guild text channels
        if not message.guild or not isinstance(message.channel, discord.TextChannel):
            return
        
        # Note message content is not actually read here, so I think this is fine even if the user opted out.
        # user: User | None = self.bot.cache.get_user(message.author)
        # if user and user.opt_out_message:
        #     return
        
        # Get sticky message for this channel, if any
        sticky_message: StickyMessage | None = self.bot.cache.get_sticky_message(message.channel.id)

        # If there is no sticky message, return
        if not sticky_message:
            return
        
        # If there is a sticky message for this channel, but the current message is sent by the bot itself and contains the same content, then we should ignore this event
        if message.author == self.bot.user and message.content == sticky_message.message:
            return
        
        # If there is a sticky message for this channel, fetch the message
        old_message: discord.Message | None = None
        if sticky_message.message_id:
            try:
                old_message = await message.channel.fetch_message(sticky_message.message_id)
            except (discord.Forbidden, discord.NotFound):
                pass
        
        # Then resend the message
        try:
            new_message: discord.Message = await message.channel.send(sticky_message.message)
        except discord.Forbidden:
            # If we lack permission to send messages in this channel, just remove the sticky message
            await self.delete_sticky_message(message.guild.id, message.channel.id)
            return

        await self.set_sticky_message_id(sticky_message, new_message.id)

        # Delete the old message, if any
        if old_message:
            try:
                await old_message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

    @Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        '''
        This event triggers whenever a message is deleted.
        When this message corresponds to any sticky message, we resend it here.

        Args:
            message (discord.Message): The deleted message
        '''
        # Only process sticky message in guild text channels
        if not message.guild or not isinstance(message.channel, discord.TextChannel):
            return

        # Get sticky message for this channel from the cache
        sticky_message: StickyMessage | None = self.bot.cache.get_sticky_message(message.channel.id)

        # If there is no sticky message or it does not correspond to the deleted message, return
        if not sticky_message or not sticky_message.message_id or sticky_message.message_id != message.id:
            return
        
        # Then resend the message
        try:
            new_message: discord.Message = await message.channel.send(sticky_message.message)
        except discord.Forbidden:
            # If we lack permission to send messages in this channel, just remove the sticky message
            async with self.bot.db.get_session() as session:
                await self.delete_sticky_message(message.guild.id, message.channel.id)
                return

        await self.set_sticky_message_id(sticky_message, new_message.id)

    @is_admin()
    @commands.hybrid_command()
    async def sticky(self, ctx: commands.Context, *, sticky_text: str | None = None) -> None:
        '''
        Adds, updates, or removes a sticky message.

        Args:
            ctx (commands.Context): The command context
            sticky_text (str | None, optional): The content of the sticky message. Pass None to remove a sticky message. Defaults to None.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild or not isinstance(ctx.author, discord.Member) or not isinstance(ctx.channel, discord.TextChannel):
            raise commands.CommandError('This command can only be used in a text channel in a server.')

        await ctx.typing()

        # Get existing sticky message and either update or delete depending on parameter sticky_text
        sticky_message: StickyMessage | None = None
        message: discord.Message | None
        try:
            message = await ctx.channel.send(sticky_text) if sticky_text else None
        except discord.Forbidden:
            raise commands.CommandError('Missing permission `send_messages` in this channel.')
        message_id: int | None = message.id if message else None
        old_message_id: int | None = None

        sticky_message = self.bot.cache.get_sticky_message(ctx.channel.id)
        if sticky_message and not sticky_text:
            old_message_id = sticky_message.message_id
            await self.delete_sticky_message(ctx.guild.id, ctx.channel.id)
        elif sticky_message and sticky_text and message_id:
            old_message_id = sticky_message.message_id
            async with self.bot.db.get_session() as session:
                await session.execute(update(StickyMessage)
                    .where(StickyMessage.guild_id == ctx.guild.id, StickyMessage.channel_id == ctx.channel.id)
                    .values(message=sticky_text, message_id=message_id))
                await session.commit()
            sticky_message.message = sticky_text
            sticky_message.message_id = message_id
            
        if not sticky_message and not sticky_text:
            raise commands.CommandError('There is no sticky message to be removed in this channel. If you are trying to create a new sticky message, please provide the text as argument.')

        if old_message_id:
            try:
                old_message: discord.Message = await ctx.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.Forbidden:
                pass

        if not sticky_text:
            await ctx.send('Sticky message deleted successfully.')
            return
        
        if sticky_text and sticky_message:
            await ctx.send('Sticky message updated successfully.')
            return
            
        # Create new sticky message if one did not exist yet
        async with self.bot.db.get_session() as session:
            new_sticky_message: StickyMessage = StickyMessage(guild_id=ctx.guild.id, channel_id=ctx.channel.id, message=sticky_text, message_id=message_id)
            session.add(new_sticky_message)
            await session.commit()
        self.bot.cache.sticky_message(new_sticky_message)

        await ctx.send('Sticky message added successfully.')

    async def delete_sticky_message(self, guild_id: int, channel_id: int) -> None:
        '''
        Delete the sticky message for a channel from the cache and the database.
        '''
        self.bot.cache.remove_sticky_message(channel_id)
        async with self.bot.db.get_session() as session:
            await session.execute(delete(StickyMessage).where(StickyMessage.guild_id == guild_id, StickyMessage.channel_id == channel_id))
            await session.commit()

    async def set_sticky_message_id(self, sticky_message: StickyMessage, message_id: int | None) -> None:
        '''
        Update the message id of a sticky message in the cache and the database.
        '''
        sticky_message.message_id = message_id
        async with self.bot.db.get_session() as session:
            await session.execute(update(StickyMessage)
                .where(StickyMessage.guild_id == sticky_message.guild_id, StickyMessage.channel_id == sticky_message.channel_id)
                .values(message_id=message_id))
            await session.commit()

async def setup(bot: Bot) -> None:
    await bot.add_cog(Sticky(bot))
