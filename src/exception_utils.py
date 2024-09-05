def format_syntax_error(e: SyntaxError) -> str:
    '''
    Return a formatted string for the given syntax error.

    Args:
        e (SyntaxError): The syntax error.

    Returns:
        str: The formatted string
    '''
    if e.text is None:
        return f'```py\n{e.__class__.__name__}: {e}\n```'
    return f'```py\n{e.text}{"^":>{e.offset}}\n{e.__class__.__name__}: {e}```'