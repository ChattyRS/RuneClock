from typing import Sequence
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from sqlalchemy import delete
from src.checks import is_admin
from src.bot import Bot
from src.database import StickyMessage
from src.database_utils import get_sticky_messages

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
        
        # Get sticky message for this channel, if any
        async with self.bot.db.get_session() as session:
            sticky_messages: Sequence[StickyMessage] = await get_sticky_messages(session, message.guild.id, message.channel.id)
        sticky_message: StickyMessage | None = sticky_messages[0] if sticky_messages else None

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
            except discord.Forbidden:
                pass
        
        # Then resend the message
        new_message_id: int | None = None
        try:
            new_message: discord.Message = await message.channel.send(sticky_message.message)
            new_message_id = new_message.id
        except discord.Forbidden:
            # If we lack permission to send messages in this channel, just remove the sticky message
            async with self.bot.db.get_session() as session:
                await session.execute(delete(StickyMessage).where(StickyMessage.guild_id == message.guild.id and StickyMessage.channel_id == message.channel.id))
                await session.commit()
            return

        async with self.bot.db.get_session() as session:
            sticky_messages: Sequence[StickyMessage] = await get_sticky_messages(session, message.guild.id, message.channel.id)
            sticky_message = sticky_messages[0] if sticky_messages else None
            if sticky_message:
                sticky_message.message_id = new_message_id
                await session.commit()

        # Delete the old message, if any
        if old_message:
            try:
                await old_message.delete()
            except discord.Forbidden:
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
        
        # Get sticky message for this channel, if any
        sticky_message: StickyMessage | None = None
        
        async with self.bot.db.get_session() as session:
            sticky_messages: Sequence[StickyMessage] = await get_sticky_messages(session, message.guild.id, message.channel.id)
            sticky_message = sticky_messages[0] if sticky_messages else None

        # If there is no sticky message or it does not correspond to the deleted message, return
        if not sticky_message or not sticky_message.message_id or sticky_message.message_id != message.id:
            return
        
        # Then resend the message
        new_message_id: int | None = None
        try:
            new_message: discord.Message = await message.channel.send(sticky_message.message)
            new_message_id = new_message.id
        except discord.Forbidden:
            # If we lack permission to send messages in this channel, just remove the sticky message
            async with self.bot.db.get_session() as session:
                await session.execute(delete(StickyMessage).where(StickyMessage.guild_id == message.guild.id and StickyMessage.channel_id == message.channel.id))
                await session.commit()
                return

        async with self.bot.db.get_session() as session:
            sticky_messages: Sequence[StickyMessage] = await get_sticky_messages(session, message.guild.id, message.channel.id)
            sticky_message = sticky_messages[0] if sticky_messages else None
            if sticky_message:
                sticky_message.message_id = new_message_id
                await session.commit()

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

        await ctx.channel.typing()

        # Get existing sticky message and either update or delete depending on parameter sticky_text
        sticky_message: StickyMessage | None = None
        message: discord.Message | None
        try:
            message = await ctx.channel.send(sticky_text) if sticky_text else None
        except discord.Forbidden:
            raise commands.CommandError('Missing permission `send_messages` in this channel.')
        message_id: int | None = message.id if message else None
        old_message_id: int | None = None

        async with self.bot.db.get_session() as session:
            sticky_messages: Sequence[StickyMessage] = await get_sticky_messages(session, ctx.guild.id, ctx.channel.id)
            sticky_message = sticky_messages[0] if sticky_messages else None

            
            if sticky_message and not sticky_text:
                old_message_id = sticky_message.message_id
                await session.delete(sticky_message)
                await session.commit()
            elif sticky_message and sticky_text and message_id:
                old_message_id = sticky_message.message_id
                sticky_message.message = sticky_text
                sticky_message.message_id = message_id
                await session.commit()
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
            session.add(StickyMessage(guild_id=ctx.guild.id, channel_id=ctx.channel.id, message=sticky_text, message_id=message_id))
            await session.commit()

        await ctx.send('Sticky message added successfully.')

async def setup(bot: Bot) -> None:
    await bot.add_cog(Sticky(bot))
