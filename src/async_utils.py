from asyncio import gather, sleep
from typing import Coroutine

async def chunk_coroutines(coroutines: list[Coroutine], chunk_size: int, delay: int = 1) -> None:
    '''
    Execute a list of coroutines with concurrency.
    Note that the global rate limit = 50 requests per second.

    Args:
        chunk_size (int): Number of coroutines to execute concurrently
        delay (int, optional): Delay in seconds between execution of consecutive chunks. Defaults to 1.
    '''
    if not coroutines:
        return
    i: int = 0
    # Split list of coroutines into chunks to avoid rate limits
    for chunk in [coroutines[j:j + chunk_size] for j in range(0, len(coroutines), chunk_size)]:
        i += len(chunk)
        # Execute the chunk of coroutines
        await gather(*chunk)
        # Sleep for a second after each chunk of requests to avoid rate limits (all but the last chunk, because then we are already done)
        if i < len(coroutines):
            await sleep(delay)