from io import BytesIO
from imageio import imread as read_image, imwrite as write_image
from imageio.core.util import Array
from discord import File
from src.number_utils import is_int

zero_digit: list[list[int]] =  [
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 1, 0]
]
one_digit: list[list[int]] = [
    [0, 1, 0],
    [1, 1, 0],
    [0, 1, 0],
    [0, 1, 0],
    [0, 1, 0],
    [0, 1, 0],
    [0, 1, 0],
    [1, 1, 1]
]
two_digit: list[list[int]] = [
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [0, 0, 0, 0, 1],
    [0, 0, 0, 1, 0],
    [0, 0, 1, 0, 0],
    [0, 1, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 1, 1, 1, 1]
]
three_digit: list[list[int]] = [
    [0, 1, 1, 0],
    [1, 0, 0, 1],
    [0, 0, 0, 1],
    [0, 1, 1, 0],
    [0, 0, 0, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1],
    [0, 1, 1, 0]
]
four_digit: list[list[int]] = [
    [1, 0, 0, 0],
    [1, 0, 0, 0],
    [1, 0, 0, 0],
    [1, 0, 1, 0],
    [1, 0, 1, 0],
    [1, 1, 1, 1],
    [0, 0, 1, 0],
    [0, 0, 1, 0]
]
five_digit: list[list[int]] = [
    [1, 1, 1, 1],
    [1, 0, 0, 0],
    [1, 0, 0, 0],
    [1, 1, 1, 0],
    [0, 0, 0, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1],
    [0, 1, 1, 0]
]
six_digit: list[list[int]] = [
    [0, 0, 1, 1, 0],
    [0, 1, 0, 0, 1],
    [1, 0, 0, 0, 0],
    [1, 0, 1, 1, 0],
    [1, 1, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 1, 0]
]
seven_digit: list[list[int]] = [
    [1, 1, 1, 1],
    [0, 0, 0, 1],
    [0, 0, 1, 0],
    [0, 0, 1, 0],
    [0, 1, 0, 0],
    [0, 1, 0, 0],
    [1, 0, 0, 0],
    [1, 0, 0, 0]
]
eight_digit: list[list[int]] = [
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 1, 0]
]
nine_digit: list[list[int]] = [
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 0, 0, 1],
    [0, 0, 1, 1, 1],
    [0, 0, 0, 0, 1],
    [0, 0, 0, 0, 1],
    [0, 0, 0, 0, 1]
]
k_char: list[list[int]] = [
    [1, 0, 0, 0, 1],
    [1, 0, 0, 1, 0],
    [1, 0, 1, 0, 0],
    [1, 1, 0, 0, 0],
    [1, 1, 0, 0, 0],
    [1, 0, 1, 0, 0],
    [1, 0, 0, 1, 0],
    [1, 0, 0, 0, 1]
]
m_char: list[list[int]] = [
    [1, 0, 0, 0, 1],
    [1, 1, 0, 1, 1],
    [1, 0, 1, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1]
]
minus_char: list[list[int]] = [
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [1, 1, 1, 1, 1],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0]
]

digits: list[list[list[int]]] = [zero_digit, one_digit, two_digit, three_digit, four_digit, five_digit, six_digit, seven_digit, eight_digit, nine_digit, k_char, m_char, minus_char]

zero_digit_rs3: list[list[int]] =  [
    [0, 0, 1, 0, 0],
    [0, 1, 0, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 0, 1, 0],
    [0, 0, 1, 0, 0]
]
digits_rs3: list[list[list[int]]] = [zero_digit_rs3, one_digit, two_digit, three_digit, four_digit, five_digit, six_digit, seven_digit, eight_digit, nine_digit]

black: list[int] = [0, 0, 0, 255]
white: list[int] = [255, 255, 255, 255]
red: list[int] = [255, 50, 50, 255]
green: list[int] = [0, 255, 131, 255]
yellow: list[int] = [255, 255, 0, 255]
orange: list[int] = [255, 140, 0, 255]

char_index: dict[str, int] = {'K': 10, 'M': 11, '-': 12}

def get_coins_image_name(amount: int) -> str:
    '''
    Gets the name of the appropriate image for the given number of coins.

    Args:
        amount (int): The number of coins

    Returns:
        str: The corresponding image name.
    '''
    amount = abs(amount)
    if amount >= 10000:
        return 'Coins_10000_detail'
    elif amount >= 1000:
        return 'Coins_1000_detail'
    elif amount >= 250:
        return 'Coins_250_detail'
    elif amount >= 100:
        return 'Coins_100_detail'
    elif amount >= 25:
        return 'Coins_25_detail'
    elif amount >= 5:
        return 'Coins_5_detail'
    elif amount >= 1 and amount <= 5:
        return f'Coins_{amount}_detail'
    else:
         return 'Coins_1_detail'

def draw_digit(im: Array, digit: int, x: int, y: int, c: list[int], osrs: bool) -> tuple[int, int]:
    '''
    Draws a single digit onto an image.

    Args:
        im (Array): The image to draw onto
        num (int): The digit to draw
        x (int): The x-coordinate
        y (int): The y-coordinate
        c (list[int]): The colour
        osrs (bool): Whether the number should be drawn in OSRS or RS3 style.

    Returns:
        tuple[int, int]: The (x, y) coordinates where we stopped drawing.
    '''
    colour: list[int] = c
    if im.shape[2] == 3 and len(c) > 3:
        colour = colour[:3]
    elif im.shape[2] == 4 and len(c) < 4:
        colour.append(255)
    if osrs:
        pixels: list[list[int]] = digits[digit]
    else:
        pixels = digits_rs3[digit]
    x_0: int = x
    for row in reversed(pixels):
        x = x_0
        for value in reversed(row):
            if value == 1:
                im[y, x] = colour
            x -= 1
        y -= 1
    return (x-1, y)

def draw_num(im: Array, num: int, x: int, y: int, c: list[int], osrs: bool) -> None:
    '''
    Draws a number onto an image.

    Args:
        im (Array): The image to draw onto
        num (int): The number to draw
        x (int): The x-coordinate
        y (int): The y-coordinate
        c (list[int]): The colour
        osrs (bool): Whether the number should be drawn in OSRS or RS3 style.

    Raises:
        ValueError: If the given number is invalid and cannot be drawn.
    '''
    if not is_int(num):
        raise ValueError(f'Invalid Integer argument: {num}')
    else:
        num = int(num)
    digit_list: list[int] = []
    for i in range(len(str(num))):
        digit_list.append(int(str(num)[i]))
    if len(digit_list) == 1:
        x -= 3
    for digit in reversed(digit_list):
        if osrs: 
            draw_digit(im, digit, x, y, black, osrs)
            x, y = x-1, y-1
        x, _ = draw_digit(im, digit, x, y, c, osrs)
        if osrs:
            y += 1

def draw_outline_osrs(im: Array, x0: int, y0: int, c: list[int]) -> None:
    '''
    Draws an outline over a skill in the skills tab.

    Args:
        im (Array): The image to draw onto
        x0 (int): The x-coordinate
        y0 (int): The y-coordinate
        c (list[int]): The colour
    '''
    colour: list[int] = c
    if im.shape[2] == 3 and len(c) > 3:
        colour = colour[:3]
    elif im.shape[2] == 4 and len(c) < 4:
        colour.append(255)
    for x in range(x0, x0+62):
        for y in range(y0, y0+32):
            if ((y-y0 == 0 and (x-x0 >= 3 and x-x0 <= 58)) or 
                (y-y0 == 31 and (x-x0 >= 3 and x-x0 <= 58)) or
                (x-x0 == 0 and (y-y0 >= 3 and y-y0 <= 28)) or
                (x-x0 == 61 and (y-y0 >= 3 and y-y0 <= 28))):
                im[y, x] = colour
            elif ((x-x0 == 3 and y-y0 < 3) or
                  (y-y0 == 3 and x-x0 < 3) or
                  (x-x0 == 2 and y-y0 == 2)):
                im[y, x] = colour
            elif ((x-x0 == 58 and y-y0 < 3) or
                  (y-y0 == 3 and x-x0 > 58) or
                  (x-x0 == 59 and y-y0 == 2)):
                im[y, x] = colour
            elif ((x-x0 == 3 and y-y0 > 28) or
                  (y-y0 == 28 and x-x0 < 3) or
                  (x-x0 == 2 and y-y0 == 29)):
                im[y, x] = colour
            elif ((x-x0 == 58 and y-y0 > 28) or
                  (y-y0 == 28 and x-x0 > 58) or
                  (x-x0 == 59 and y-y0 == 29)):
                im[y, x] = colour

def draw_outline_rs3(im: Array, x0: int, y0: int, c: list[int]) -> None:
    '''
    Draws an outline over a skill in the skills tab.

    Args:
        im (Array): The image to draw onto
        x0 (int): The x-coordinate
        y0 (int): The y-coordinate
        c (list[int]): The colour
    '''
    colour: list[int] = c
    if im.shape[2] == 3 and len(c) > 3:
        colour = colour[:3]
    elif im.shape[2] == 4 and len(c) < 4:
        colour.append(255)
    for x in range(x0, x0+58):
        for y in range(y0, y0+25):
            if x == x0 or x == x0+57 or y == y0 or y == y0+24:
                im[y, x] = colour

def enlarge_digit(digit: list[list[int]], factor: int) -> list[list[int]]:
    '''
    Doubles the size of an image *factor* times.

    Args:
        digit (list[list[int]]): The digit to enlarge
        factor (int): The factor by which to enlarge the digit

    Returns:
        list[list[int]]: Enlarged version of the digit
    '''
    for _ in range(factor-1):
        ldigit: list[list[int]] = []
        for row in digit:
            lrow: list[int] = [row[int(i/2)] for i in range(len(row)*2)]
            ldigit.append(lrow)
            ldigit.append(lrow)
        digit = ldigit
    return digit

def draw_char(img: Array, char: str, x: int, y: int, c: list[int], size: int) -> tuple[int, int]:
    '''
    Draws a character on an image at (x, y)

    Args:
        img (Array): The image to draw onto
        char (str): The character to draw
        x (int): The x-coordinate
        y (int): The y-coordinate
        c (list[int]): The colour
        size (int): The size

    Returns:
        tuple[int, int]: The (x, y) coordinates where we stopped drawing
    '''
    colour: list[int] = c
    if img.shape[2] == 3 and len(c) > 3:
        colour = colour[:3]
    elif img.shape[2] == 4 and len(c) < 4:
        colour.append(255)
    digit: list[list[int]] = digits[int(char) if is_int(char) else char_index[char]]
    pixels: list[list[int]] = enlarge_digit(digit, size)
    x_0: int = x
    for row in reversed(pixels):
        x = x_0
        for value in reversed(row):
            if value == 1:
                img[y, x] = colour
            x -= 1
        y -= 1
    return (x-1, y)

def draw_gp(img: Array, amount: int) -> None:
    '''
    Draw an amount over an image of RuneScape coins.

    Args:
        img (Array): The image to draw onto
        amount (int): The amount
    '''
    colour: list[int] = green if amount >= 10000000 else white if amount >= 100000 else yellow if amount >= 0 else red
    amount = round(amount, -6) if abs(amount) >= 10000000 else round(amount, -3) if abs(amount) >= 100000 else amount
    amount_str = str(amount)
    if amount >= 10000000 or amount <= -10000000:
        amount_str: str = amount_str[::-1].replace('000000', 'M', 1)[::-1]
    elif amount >= 100000 or amount <= -100000:
        amount_str = amount_str[::-1].replace('000', 'K', 1)[::-1]
    size = 5
    for i, char in enumerate(amount_str):
        draw_char(img, char, (int(5*(2**size)/2)-1)*(i+1)+i*(2**size), int(8*(2**size)/2)-1, colour, size)

def get_coins_image(amount: int) -> File:
    '''
    Get an image for the given amount of coins.

    Args:
        amount (int): The amount

    Returns:
        discord.File: The image file
    '''
    # Get base coins image
    coins: Array = read_image(f'images/{get_coins_image_name(amount)}.png')

    # Draw amount
    draw_gp(coins, amount)

    write_image('images/coins.png', coins)
    with open('images/coins.png', 'rb') as f:
        coins_image = BytesIO(f.read())
    coins_image = File(coins_image, filename='coins.png')
    return coins_image