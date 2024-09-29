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
    with codecs.open('./data/config.json', 'r', encoding='utf-8-sig') as doc:
        return json.load(doc)

config = get_config()