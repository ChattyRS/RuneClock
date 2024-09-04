import codecs
import json
from typing import Any

config: dict[str, Any] = {}

def get_config() -> dict[str, Any]:
    '''
    Load config file with necessary information.

    Returns:
        dict[str, Any]: The configuration dictionary.
    '''
    if config:
        return config
    with codecs.open('../data/config.json', 'r', encoding='utf-8-sig') as doc:
        return json.load(doc)

config = get_config()

item_emojis: list[list[str]] = [
    ['Uncharted island map', 'uncharted_island_map'],
    ['Livid plant', 'livid_plant'],
    ['Crystal triskelion', 'crystal_triskelion'],
    ['Deathtouched dart', 'deathtouched_dart'],
    ['Gift for the Reaper', 'gift_for_the_reaper'],
    ['Slayer VIP Coupon', 'slayer_vip_coupon'],
    ['Shattered anima', 'shattered_anima'],
    ['Unstable air rune', 'unstable_air_rune'],
    ['Dungeoneering Wildcard', 'dungeoneering_wildcard'],
    ['Taijitu', 'taijitu'],
    ['Harmonic dust', 'harmonic_dust'],
    ['Sacred clay', 'sacred_clay'],
    ['Advanced pulse core', 'advanced_pulse_core'],
    ['Silverhawk down', 'silverhawk_down'],
    ['Barrel of bait', 'fishing_boost'],
    ['Broken fishing rod', 'fishing_boost'],
    ['Tangled fishbowl', 'fishing_boost'],
    ['Message in a bottle', 'message_in_a_bottle'],
    ['Dragonkin lamp', 'dragonkin_lamp'],
    ['Starved ancient effigy', 'starved_ancient_effigy'],
    ['Unfocused damage enhancer', 'unfocused_damage_enhancer'],
    ['Unfocused reward enhancer', 'unfocused_reward_enhancer'],
    ['Daily D&D token', 'dnd_token_daily'],
    ['Weekly D&D token', 'dnd_token_weekly'],
    ['Monthly D&D token', 'dnd_token_monthly'],
    ['Small goebie burial charm', 'mazcab_reputation'],
    ['Goebie burial charm', 'mazcab_reputation'],
    ['Large goebie burial charm', 'mazcab_reputation'],
    ['Small Menaphite gift offering', 'menaphos_reputation'],
    ['Medium Menaphite gift offering', 'menaphos_reputation'],
    ['Large Menaphite gift offering', 'menaphos_reputation'],
    ['Anima crystal', 'anima_crystal']
]