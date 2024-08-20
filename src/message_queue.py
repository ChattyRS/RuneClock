import asyncio
import discord
from collections import deque
import logging
from utils import chunk_coroutines
import sys
sys.path.append('../')


class QueueMessage:
    channel: discord.TextChannel
    message: str | None
    embed: discord.Embed | None

    def __init__(self, channel: discord.TextChannel, message: str | None = None, embed: discord.Embed | None = None) -> None:
        self.channel = channel

        if not message and not embed:
            raise Exception('Tried to create an empty message.')

        self.message = message
        self.embed = embed

    async def send(self) -> None:
        '''
        Safely send a message to a text channel.
        Safely here means that any exceptions are handled.
        '''
        try:
            if self.embed:
                await self.channel.send(self.message, embed=self.embed)
            else:
                await self.channel.send(self.message)
        except discord.Forbidden:
            pass
        except Exception as e:
            error: str = f'Encountered error while sending a message:\n{type(e).__name__}: {e}'
            logging.critical(error)
            print(error)

class MessageQueue(deque[QueueMessage]):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            iterable=kwargs.pop('iterable', []),
            maxlen=kwargs.pop('maxlen', None)
        )

    async def send_queued_messages(self) -> None:
        '''
        Sends queued messages in chunks according to rate limit availability.
        The global rate limit is 50 requests per second. 
        To be on the safe side, we work with a max of 40 requests per second here.
        The queue is checked every 25 ms, or whenever the rate limit has expired.
        Numbers here assume that any processing is instant.
        '''
        rate_limit: int = 40
        # Keeps track of messages sent in previous iterations
        # Each element denotes the number of messages sent in a 25 ms chunk
        messages_sent: deque[int] = deque([0 for _ in range(rate_limit)], rate_limit)
        while True:
            current: int = sum(messages_sent)
            limit: int = rate_limit - current
            
            messages: list[QueueMessage] = [self.popleft() for _ in range(min(len(self), limit))]
            await chunk_coroutines([message.send() for message in messages], rate_limit)
            sent: int = len(messages)

            # Wait to avoid hitting rate limits.
            # However, we don't want to simply wait a second between every time we check the message queue.
            # Instead, as a baseline we check the queue every 25 ms.
            # However, when we hit the rate limit, we wait until the rate limit has expired
            first_change: int = messages_sent.popleft()
            while first_change == 0 and len(messages_sent) > 0 and sum(messages_sent) >= rate_limit:
                first_change = messages_sent.popleft()
            iterations_to_wait: int = rate_limit - len(messages_sent)
            messages_sent.append(sent)
            while len(messages_sent) < rate_limit:
                messages_sent.append(0)
            
            await asyncio.sleep(iterations_to_wait / rate_limit)