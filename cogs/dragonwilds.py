import discord
from discord.ext import commands
from discord.ext.commands import Cog
from datetime import datetime, UTC
import aiohttp
from src.bot import Bot
from src.checks import is_owner
from src.process_utils import is_process_running, kill_process_by_name, run_batch_script

class Dragonwilds(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @commands.group(invoke_without_command=True)
    async def dragonwilds(self, ctx: commands.Context) -> None:
        '''
        Returns the status of the RS Dragonwilds server.
        '''
        self.bot.increment_command_counter()
        await ctx.typing()

        url: str = self.bot.config['dragonwilds_api_url']
        status = None
        try:
            async with self.bot.aiohttp.get(url, timeout=aiohttp.ClientTimeout(total=3)) as r:
                if r.status != 200:
                    raise commands.CommandError(message=f'Failed to retrieve status from Dragonwilds API. Server status is unknown.')
                status = await r.json()
        except TimeoutError:
            raise commands.CommandError(message=f'Request to Dragonwilds API timed out. Server status is unknown.')
        except:
            raise commands.CommandError(message=f'Failed to connect to Dragonwilds API. Server status is unknown.')

        if not status or not status['status']:
            raise commands.CommandError(message=f'API request was successful but did not provide status. Server status is unknown.')

        now: datetime = datetime.now(UTC).replace(microsecond=0)
        server_status: str = status['status']
        txt: str = 'Online :white_check_mark:' if server_status.lower() == 'online' else 'Offline :x:'
        embed = discord.Embed(title='**Status**', colour=0x00e400, timestamp=now, description=txt)
        
        server: str = f'**World:** {status['world']}\n**Players:** {status['players_online']}/{status['max_players']}\n**Last save:** {status['last_save']}'
        embed.add_field(name='__Server__', value=server)

        embed.set_author(name='@schattie', url='https://github.com/ChattyRS/RuneClock', icon_url=self.bot.config['profile_picture_url'])
        embed.set_thumbnail(url=ctx.me.display_avatar.url)

        await ctx.send(embed=embed)
        

    @dragonwilds.command()
    @is_owner()
    async def stop(self, ctx: commands.Context) -> None:
        '''
        Stops the RS Dragonwilds server.
        '''
        self.bot.increment_command_counter()
        if not is_process_running(self.bot.config['dragonwilds_executable_name']):
            raise commands.CommandError(message=f'Dragonwilds server is not currently running.')
        kill_process_by_name(self.bot.config['dragonwilds_executable_name'])
        await ctx.send(f'Server stopped.')

    @dragonwilds.command()
    @is_owner()
    async def start(self, ctx: commands.Context) -> None:
        '''
        Starts the RS Dragonwilds server.
        '''
        self.bot.increment_command_counter()
        if is_process_running(self.bot.config['dragonwilds_executable_name']):
            raise commands.CommandError(message=f'Dragonwilds server is already running.')
        run_batch_script(self.bot.config['dragonwilds_start_script_path'])
        await ctx.send(f'Server started.')

    @dragonwilds.command()
    @is_owner()
    async def restart(self, ctx: commands.Context) -> None:
        '''
        Restarts the RS Dragonwilds server.
        '''
        self.bot.increment_command_counter()
        if not is_process_running(self.bot.config['dragonwilds_executable_name']):
            raise commands.CommandError(message=f'Dragonwilds server is not currently running.')
        kill_process_by_name(self.bot.config['dragonwilds_executable_name'])
        run_batch_script(self.bot.config['dragonwilds_start_script_path'])
        await ctx.send(f'Server restarted.')

    @dragonwilds.command()
    @is_owner()
    async def update(self, ctx: commands.Context) -> None:
        '''
        Restarts the RS Dragonwilds server.
        '''
        self.bot.increment_command_counter()
        if is_process_running(self.bot.config['dragonwilds_executable_name']):
            raise commands.CommandError(message=f'Dragonwilds server is currently running. Please stop it before updating.')
        run_batch_script(self.bot.config['dragonwilds_update_script_path'])
        await ctx.send(f'Server update initiated.')

async def setup(bot: Bot) -> None:
    await bot.add_cog(Dragonwilds(bot))