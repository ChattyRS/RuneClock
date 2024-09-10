from multiprocessing.managers import DictProxy, SyncManager
from typing import Any
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from bot import Bot
import sys
import re
import matplotlib.pyplot as plt
import numpy as np
from number_utils import is_int, is_float, format_float
from unit_conversion_utils import units, unit_aliases, get_alias
import io
import multiprocessing
from math_constants import numeric
from math_utils import calculate, format_input, format_output, prettify_input, solve_for_x, plot_func

np.seterr(all='raise')

class Mathematics(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @commands.command(pass_context=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def math(self, ctx: commands.Context, *formulas) -> None:
        '''
        Calculates the result of a given mathematical problem.
        Supported operations:
        Basic: +, -, *, /
        Modulus: % or mod
        Powers: ^
        Square roots: sqrt()
        Factorial: !
        Logarithms: log(,[base]) (default base=e)
        Absolute value: abs()
        Rounding: round(), floor(), ceil()
        Trigonometry: sin(), cos(), tan() (in radians)
        Parentheses: ()
        Constants: pi, e, phi, tau, etc...
        Complex/imaginary numbers: i
        Infinity: inf
        Sum: sum(start, end, f(x)) (start and end inclusive)
        Product: product(start, end, f(x)) (start and end inclusive)
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()
        
        formula: str = ' '.join(formulas).strip()
        if not formula:
            raise commands.CommandError(message=f'Required argument missing: `formula`.')
        try:
            input: str = format_input(formula.lower(), 0)

            manager: SyncManager = multiprocessing.Manager()
            val: DictProxy = manager.dict()

            p = multiprocessing.Process(target=calculate, args=(input, val))
            p.start()
            p.join(10)

            if p.is_alive():
                p.terminate()
                p.join()
                raise commands.CommandError('Execution timed out.')

            result: Any = val['val']

            output: str = format_output(result)
            formula = prettify_input(formula)
            embed = discord.Embed(title='Math', description=f'`{formula} = {output}`')
            embed.set_footer(text='Wrong? Please let me know! DM @schattie')
            await ctx.send(embed=embed)
        except Exception as e:
            raise commands.CommandError(message=f'Invalid mathematical expression:\n```{e}```')

    @commands.command(pass_context=True, aliases=['plot'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def graph(self, ctx: commands.Context, start: float, end: float, *formulas) -> None:
        '''
        Plots a given mathematical function
        Arguments: start, end, f(x)
        Supported operations:
        Basic: +, -, *, /
        Modulus: % or mod
        Powers: ^
        Square roots: sqrt()
        Logarithms: log() (base=e)
        Absolute value: abs()
        Rounding: round(), floor(), ceil()
        Trigonometry: sin(), cos(), tan() (in radians)
        Parentheses: ()
        Constants: pi, e, phi, tau, etc...
        Example: graph -10 10 x
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()
        formula: str = ' '.join(formulas).strip()
        if not is_float(start) or not is_float(end):
            raise commands.CommandError(message=f'Invalid argument(s): `start/end`.')
        elif start >= end:
            raise commands.CommandError(message=f'Invalid arguments: `start`, `end`.')
        if not formula:
            raise commands.CommandError(message=f'Required argument missing: `formula`.')
        try:
            input: str = format_input(formula.lower(), 1)

            x: np.ndarray = np.linspace(start, end, 250)

            plt.style.use('dark_background')
            fig, ax = plt.subplots()

            manager: SyncManager = multiprocessing.Manager()
            val: DictProxy = manager.dict()

            p = multiprocessing.Process(target=plot_func, args=(x, input, val))
            p.start()
            p.join(10)

            if p.is_alive():
                p.terminate()
                p.join()
                raise commands.CommandError('Execution timed out.')
            
            y: list = [v for v in val.values()]

            potential_error = y[len(y)-1]
            if isinstance(potential_error, Exception):
                raise potential_error

            plt.plot(x, y, color='#47a0ff')

            ax.yaxis.grid()
            ax.xaxis.grid()
            plt.xlim(start, end)
            plt.savefig('images/math_graph.png', transparent=True)
            plt.close(fig)

            with open('images/math_graph.png', 'rb') as f:
                file = io.BytesIO(f.read())
        
            image = discord.File(file, filename='math_graph.png')

            formula = prettify_input(formula)
            embed = discord.Embed(title='Graph', description=f'`𝘧(𝓍) = {formula}`')
            embed.set_footer(text='Wrong? Please let me know! DM @schattie')
            embed.set_image(url=f'attachment://math_graph.png')
            await ctx.send(file=image, embed=embed)
        except Exception as e:
            raise commands.CommandError(message=f'Invalid mathematical expression: \n```{e}```')

    @commands.command(pass_context=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def solve(self, ctx: commands.Context, *formulas) -> None:
        '''
        Solves a given equation for x.
        Supported operations:
        Basic: +, -, *, /
        Powers: ^
        Square roots: sqrt()
        Logarithms: log() (base e)
        Parentheses: ()
        Constants: pi, e, phi, tau, etc...
        Trigonometry: sin(), cos(), tan() (in radians)
        Complex/imaginary numbers: i
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()
        
        formula: str = ' '.join(formulas).strip()
        if not formula:
            raise commands.CommandError(message=f'Required argument missing: `formula`.')
        try:
            input: str = format_input(formula.lower(), 2)

            manager: SyncManager = multiprocessing.Manager()
            val: DictProxy = manager.dict()

            p = multiprocessing.Process(target=solve_for_x, args=(input, val))
            p.start()
            p.join(10)

            if p.is_alive():
                p.terminate()
                p.join()
                raise commands.CommandError('Execution timed out.')
            
            solutions: list = [sol for sol in val.values()]

            if len(solutions) == 0:
                output = 'False'
            elif len(solutions) == 1:
                output: str = f'𝓍 = {solutions[0]}'.lower()
            else:
                output = ''
                for i, sol in enumerate(solutions):
                    if not i == 0:
                        output += ' ∨ '
                    output += f'𝓍 = {sol}'.lower()

            output = format_output(output)
            formula = prettify_input(formula)
            
            embed = discord.Embed(title='Solve', description=f'{formula}\n```{output}```')
            embed.set_footer(text='Wrong? Please let me know! DM @schattie')
            await ctx.send(embed=embed)
        except Exception as e:
            raise commands.CommandError(message=f'Invalid mathematical expression:\n```{e}```')

    @commands.command()
    async def convert(self, ctx: commands.Context, value: str | float | int = '', unit: str = '', new_unit: str = '') -> None:
        '''
        Converts given unit to new unit.
        Default value = 1
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not value or not unit:
            raise commands.CommandError(message=f'Required argument(s) missing: `value/unit`.')
        elif not new_unit:
            new_unit = unit
            unit = str(value)
            value = 1

        unit = unit.lower().replace(' ', '')
        new_unit = new_unit.lower().replace(' ', '')

        if not is_float(value):
            raise commands.CommandError(message=f'Invalid argument: `{value}`.')
        elif is_int(value):
            value = int(value)
        else:
            value = float(value)

        if value > sys.maxsize:
            raise commands.CommandError(message=f'Invalid argument: `{value}`. This value is too high.')

        if not unit in units:
            if not any(unit in alias for alias in unit_aliases):
                raise commands.CommandError(message=f'Invalid argument: `{unit}`.')
            else:
                unit = get_alias(unit)


        conversion_units: dict[str, numeric] = units[unit]
        if new_unit in conversion_units:
            factor = conversion_units[new_unit]
        else:
            if not any(new_unit in alias for alias in unit_aliases):
                raise commands.CommandError(message=f'Invalid argument: `{new_unit}`.')
            else:
                new_unit = get_alias(new_unit)
                if new_unit in conversion_units:
                    factor = conversion_units[new_unit]
                else:
                    if not any(unit in alias for alias in unit_aliases):
                        raise commands.CommandError(message=f'Incompatible units: `{unit}`, `{new_unit}`.')
                    else:
                        unit = get_alias(unit)
                        conversion_units = units[unit]
                        if new_unit in conversion_units:
                            factor = conversion_units[new_unit]
                        else:
                            new_unit = get_alias(new_unit)
                            if new_unit in conversion_units:
                                factor = conversion_units[new_unit]
                            else:
                                raise commands.CommandError(message=f'Incompatible units: `{unit}`, `{new_unit}`.')

        if isinstance(factor, int) or isinstance(factor, float):
            new_value: str | float | int = value * factor
        else:
            new_value = eval(f'{value}{factor}')
        new_value = str(new_value).replace('e', ' • 10^').replace('+', '')

        await ctx.send(f'{value} {unit} = `{new_value} {new_unit}`')

    @commands.command(name='units')
    async def get_units(self, ctx: commands.Context) -> None:
        '''
        List of units supported by convert command.
        '''
        self.bot.increment_command_counter()

        txt: str = ''
        prev: dict[str, numeric] = {}
        for unit in units:
            if prev:
                if unit in prev:
                    txt += ', '
                else:
                    txt += '\n'
            txt += unit
            prev = units[unit]

        await ctx.send(f'```{txt}```')
    
    @commands.command(aliases=['sci'])
    async def scientific(self, ctx: commands.Context, *number) -> None:
        '''
        Convert a number literal to scientific notation and vice versa.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not number:
            raise commands.CommandError(message='No input. Please give a number literal as argument.')
        
        input: str = ' '.join(number)

        input = input.replace(' ', '').replace(',', '')
        input = input.replace('*10^', 'e')
        input = input.replace('x10^', 'e')
        input = input.replace('•10^', 'e')

        if 'e' in input: # convert from scientific notation to number
            num: str | float = input[:input.index('e')]
            exp: str | float = input[input.index('e')+1:]
            if not is_float(num) or not is_float(exp):
                raise commands.CommandError(message=f'Invalid input: `{input}`. Please give a number literal as argument.')
            num, exp = float(num), float(exp)
            try:
                result = num * (10**exp)
            except Exception as e:
                raise commands.CommandError(message=f'Invalid input: `{input}`. Error: {e}')
            output: str = format_float(result)
        else: # convert from number literal to scientific notation
            if not is_float(input):
                raise commands.CommandError(message=f'Invalid input: `{input}`. Please give a number literal as argument.')

            # Calculate result
            num = input if '.' in input else input + '.0'
            exp = 0
            while num.index('.') > 1:
                decimal_index = num.index('.')
                num = num[:decimal_index-1] + '.' + num[decimal_index-1:].replace('.', '')
                exp += 1

            # Remove non-significant digits and trailing decimal point
            significant_digits = max([i for i, d in enumerate([n for n in num if re.match(r'[\d]', n)]) if d != '0']) + 1
            digits: int = len([i for i in num if re.match(r'[\d]', i)])
            while digits > significant_digits:
                num = num[:len(num)-1]
                digits = len([i for i in num if re.match(r'[\d]', i)])
            if num.endswith('.'):
                num = num[:len(num)-1]
            
            output = f'{num} • 10^{exp}'
        
        if len(output) < 1998:
            await ctx.send(f'`{output}`')
        else:
            raise commands.CommandError(message=f'Error: output exceeds character limit.')


async def setup(bot: Bot) -> None:
    await bot.add_cog(Mathematics(bot))
