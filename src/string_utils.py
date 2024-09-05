def remove_code_blocks(content: str) -> str:
    '''
    Automatically removes code blocks from the given code string.

    Args:
        content (str): The string containing code blocks.

    Returns:
        str: The cleaned up string
    '''
    # remove ```py\n```
    if content.startswith('```') and content.endswith('```'):
        return '\n'.join(content.split('\n')[1:-1])
    # remove `foo`
    return content.strip('` \n')