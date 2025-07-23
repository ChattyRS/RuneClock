from copy import deepcopy
import random
from typing import Any

from src.bot import Bot

wom_skills: list[str] = [
    'overall',
    'attack',
    'defence',
    'strength',
    'hitpoints',
    'ranged',
    'prayer',
    'magic',
    'cooking',
    'woodcutting',
    'fletching',
    'fishing',
    'firemaking',
    'crafting',
    'smithing',
    'mining',
    'herblore',
    'agility',
    'thieving',
    'slayer',
    'farming',
    'runecrafting',
    'hunter',
    'construction'
]

wom_bosses: list[str] = [
    'abyssal_sire',
    'alchemical_hydra',
    'amoxliatl',
    'araxxor',
    'artio',
    'barrows_chests',
    'bryophyta',
    'callisto',
    'calvarion',
    'cerberus',
    'chambers_of_xeric',
    'chambers_of_xeric_challenge_mode',
    'chaos_elemental',
    'chaos_fanatic',
    'commander_zilyana',
    'corporeal_beast',
    'crazy_archaeologist',
    'dagannoth_prime',
    'dagannoth_rex',
    'dagannoth_supreme',
    'deranged_archaeologist',
    'doom_of_mokhaiotl',
    'duke_sucellus',
    'general_graardor',
    'giant_mole',
    'grotesque_guardians',
    'hespori',
    'kalphite_queen',
    'king_black_dragon',
    'kraken',
    'kreearra',
    'kril_tsutsaroth',
    'lunar_chests',
    'mimic',
    'nex',
    'nightmare',
    'phosanis_nightmare',
    'obor',
    'phantom_muspah',
    'sarachnis',
    'scorpia',
    'scurrius',
    'skotizo',
    'sol_heredit',
    'spindel',
    'tempoross',
    'the_gauntlet',
    'the_corrupted_gauntlet',
    'the_hueycoatl',
    'the_leviathan',
    'the_royal_titans',
    'the_whisperer',
    'theatre_of_blood',
    'theatre_of_blood_hard_mode',
    'thermonuclear_smoke_devil',
    'tombs_of_amascut',
    'tombs_of_amascut_expert',
    'tzkal_zuk',
    'tztok_jad',
    'vardorvis',
    'venenatis',
    'vetion',
    'vorkath',
    'wintertodt',
    'yama',
    'zalcano',
    'zulrah'
]

wom_clues: list[str] = [
    'clue_scrolls_all',
    'clue_scrolls_beginner',
    'clue_scrolls_easy',
    'clue_scrolls_medium',
    'clue_scrolls_hard',
    'clue_scrolls_elite',
    'clue_scrolls_master'
]

wom_minigames: list[str] = [
    'league_points',
    'bounty_hunter_hunter',
    'bounty_hunter_rogue',
    'last_man_standing',
    'pvp_arena',
    'soul_wars_zeal',
    'guardians_of_the_rift',
    'colosseum_glory',
    'collections_logged'
]

wom_efficiency: list[str] = ['ehp', 'ehb']

wom_metrics: list[str] = wom_skills + wom_bosses + wom_clues + wom_minigames + wom_efficiency

def choose_metric(exclude: list[str] = [], type: str = '') -> str:
    '''
    Choose a WiseOldMan metric.

    Args:
        exclude (list[str], optional): List of metrics to exlude. Defaults to [].
        type (str, optional): The type of metric too choose form.

    Raises:
        Exception: If no metric can be found.

    Returns:
        str: The metric
    '''
    type = type.lower().strip()

    options: list[str] = deepcopy(wom_metrics)
    if 'skill' in type:
        options = deepcopy(wom_skills)
    elif 'boss' in type:
        options = deepcopy(wom_bosses)
    elif 'clue' in type:
        options = deepcopy(wom_clues)
    elif 'minigame' in type:
        options = deepcopy(wom_minigames)
    elif 'efficiency' in type:
        options = deepcopy(wom_efficiency)

    for opt in exclude:
        if opt in options:
            options.remove(opt)

    if not options:
        raise Exception('No options to choose from')

    return random.choice(options)

async def get_player_details(bot: Bot, username: str):
    '''
    Get player details from WOM.

    Args:
        bot (Bot): The bot
        username (str): The player username

    Returns:
        _type_: The player details, or None if not found.
    '''
    encoded_username: str = username.replace(' ', '%20')
    url: str = f'https://api.wiseoldman.net/v2/players/{encoded_username}'
    async with bot.aiohttp.get(url, headers={'x-user-agent': bot.config['wom_user_agent'], 'x-api-key': bot.config['wom_api_key']}) as r:
        # If successful, return the data from WOM
        if r.status >= 200 and r.status < 300:
            return await r.json()

    return None

async def add_group_member(bot: Bot, verification_code: str, group_id: int, username: str, role_name: str) -> bool:
    '''
    Add a member to a WOM group.

    Args:
        bot (Bot): The bot
        verification_code (str): The WOM verification code
        group_id (int): The group ID
        username (str): The username to add
        role_name (str): The role with which the user should be added

    Returns:
        bool: Boolean indicating whether the request was successful
    '''
    url: str = f'https://api.wiseoldman.net/v2/groups/{group_id}/members'
    payload: dict[str, Any] = {'verificationCode': verification_code}
    payload['members'] = [{'username': username, 'role': role_name}]
    async with bot.aiohttp.post(url, json=payload, headers={'x-user-agent': bot.config['wom_user_agent'], 'x-api-key': bot.config['wom_api_key']}) as r:
        return r.status >= 200 and r.status < 300
    
async def get_group_details(bot: Bot, group_id: int) -> dict[str, Any] | None:
    '''
    Get group details from WOM API.

    Args:
        bot (Bot): The bot
        group_id (int): The group ID

    Returns:
        dict[str, Any]: The group details
    '''
    url: str = f'https://api.wiseoldman.net/v2/groups/{group_id}'
    async with bot.aiohttp.get(url, headers={'x-user-agent': bot.config['wom_user_agent'], 'x-api-key': bot.config['wom_api_key']}) as r:
        if r.status >= 200 and r.status < 300:
            return await r.json()
    return None
