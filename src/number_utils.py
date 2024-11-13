# convert float to string without scientific notation
# https://stackoverflow.com/questions/38847690/convert-float-to-string-without-scientific-notation-and-false-precision
from decimal import Context, Decimal
from typing import Any
from discord.ext import commands

decimal_ctx = Context()
# 20 digits should be enough
decimal_ctx.prec = 20

def is_int(num: Any) -> bool:
    '''
    Checks if the given variable can be safely converted to an integer.

    Args:
        num (_type_): The variable, supposedly containing a number.

    Returns:
        bool: Boolean indicating whether the variable can be converted to an integer.
    '''
    try:
        int(num)
        return True
    except:
        return False

def is_float(num: Any) -> bool:
    '''
    Checks if the given variable can be safely converted to a floating point number.

    Args:
        num (_type_): The variable, supposedly containing a number.

    Returns:
        bool: Boolean indicating whether the variable can be converted to a floating point number.
    '''
    try:
        float(num)
        return True
    except:
        return False

def float_to_str(f: float) -> str:
    """
    Converts the given floating point number to a string.
    """
    d: Decimal = decimal_ctx.create_decimal(repr(f))
    return format(d, 'f')

def format_float(input: float) -> str:
    '''
    Converts the given floating point number to a string and formats it with a thousands separator.
    E.g. 1000.0 -> 1,000

    Args:
        input (_type_): The floating point number to format

    Returns:
        str: The formatted string
    '''
    output: str = float_to_str(input) 
    if output.endswith('.0'):
        output = output[:len(output)-2]
    end: str = ''
    if output.find('.') != -1:
        end = output[output.find('.'):]
        output = output[:output.find('.')]
    index: int = len(output)-2
    while index >= 0:
        if (len(output.replace(',', '')) - 1 - index) % 3 == 0:
            output = output[:index+1] + ',' + output[index+1:]
        index -= 1
    output += end
    return output

def emoji_from_digit(digit: int) -> str:
    '''
    Converts a digit (0-9) to an emoji, e.g. 1 -> 1️⃣

    Args:
        digit (int): Digit (0-9)

    Returns:
        str: Emoji
    '''
    if digit < 0 or digit > 9:
        raise commands.CommandError(message=f'Invalid digit: `{digit}`. Digit must be between 0 and 9.')
    emoji: dict[int, str] = {
        0: '0️⃣',
        1: '1️⃣',
        2: '2️⃣',
        3: '3️⃣',
        4: '4️⃣',
        5: '5️⃣',
        6: '6️⃣',
        7: '7️⃣',
        8: '8️⃣',
        9: '9️⃣'
    }
    return emoji[digit]

def emoji_from_number(num: int) -> str:
    '''
    Converts a number to one or more emojis, e.g. 1 -> 1️⃣

    Args:
        num (int): Number

    Returns:
        str: Emoji(s)
    '''
    num_str: str = str(num)
    emojis: str = ''
    for digit in num_str:
        emojis += emoji_from_digit(int(digit))
    return emojis