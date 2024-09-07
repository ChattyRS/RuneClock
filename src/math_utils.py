import cmath
import math
from multiprocessing.managers import DictProxy
import re
from typing import Any
import numpy as np
import sympy
from math_constants import numeric, pi, alpha, delta, theta, tau, phi, gamma, lambda_var, psi, rho, e, i, inf # unused constants may be accessed through the use of 'eval'
from math_utils import numeric, pattern_math, legal_math, pattern_graph, legal_graph, pattern_solve, legal_solve

pattern_math: str = r'(?<=[0-9a-z])(?<!log)(?<!sqrt)(?<!floor)(?<!ceil)(?<!sin)(?<!cos)(?<!tan)(?<!round)(?<!abs)(?<!inf)(?<!x)(?<!sum)(?<!product)(?<!wrap_fn)\('
legal_math: list[str] = ['log', 'sqrt', 'floor', 'ceil', 'sin', 'cos', 'tan', 'round', 'abs', 'pi', 'alpha', 'delta', 'theta', 'tau', 'phi', 'gamma', 'lambda', 'psi', 'rho', 'e', 'i', 'inf', 'mod', 'x', 'sum', 'product']
pattern_graph: str = r'(?<=[0-9a-z])(?<!log)(?<!sqrt)(?<!floor)(?<!ceil)(?<!sin)(?<!cos)(?<!tan)(?<!round)(?<!abs)(?<!x)\('
legal_graph: list[str] = ['log', 'sqrt', 'floor', 'ceil', 'sin', 'cos', 'tan', 'round', 'abs', 'pi', 'alpha', 'delta', 'theta', 'tau', 'phi', 'gamma', 'lambda', 'psi', 'rho', 'e', 'mod', 'x']
pattern_solve: str = r'(?<=[0-9a-zA-Z])(?<!log)(?<!sqrt)(?<!sin)(?<!cos)(?<!tan)(?<!x)\('
legal_solve: list[str] = ['log', 'sqrt', 'sin', 'cos', 'tan', 'pi', 'alpha', 'delta', 'theta', 'tau', 'phi', 'gamma', 'lambda', 'psi', 'rho', 'e', 'x', 'i']



def calcsum(start: int, end: int, f: str | Any) -> numeric:
    '''
    Calculates the sum of the given function f(x) from given start to end (fixed steps of 1).

    Args:
        start (int): Start x
        end (int): End x
        f (str): The function of x to sum

    Returns:
        numeric: The sum result
    '''
    if not isinstance(f, str):
        f = str(f)
    sum: numeric = 0
    for index in range(start,end+1):
        res: numeric = eval(f.replace('x', str(index)))
        sum += res
    return sum

def calcproduct(start: int, end: int, f: str | Any) -> numeric:
    '''
    Calculates the product of function f(x) from given start to end (fixed steps of 1).

    Args:
        start (int): Start x
        end (int): End x
        f (str | Any): The function of x

    Returns:
        numeric: The product result
    '''
    if not isinstance(f, str):
        f = str(f)
    product = 1
    for index in range(start,end+1):
        res: Any = eval(f.replace('x', str(index)))
        product *= res
    return product

def wrap_fn(fn: str, input: numeric) -> numeric:
    '''
    Wraps function calls to convert complex to real numbers.

    Args:
        fn (str): The function
        input (numeric): The input to the function

    Returns:
        numeric: The result
    '''
    return eval(f'{fn}({input}{".real" if hasattr(input, "real") and input.imag == 0 else ""})')

def calculate(input: str, val: DictProxy) -> None:
    '''
    Calculate the result of a mathematical expression.
    The result is written under key 'val' in the input dictionary of the same name.

    Args:
        input (str): The input to evaluate
        val (DictProxy): The dictionary proxy to write the result to.
    '''
    val['val'] = eval(input)

def format_input(input: str, style: int) -> str:
    '''
    Sanitize and format the user-input mathematical expression
    Style 0 = math, 1 = graph, 2 = solve

    Args:
        input (str): The input string to be formatted
        style (int): The style in which to format the input

    Raises:
        ValueError: If there is an illegal set of characters in the input string
        ValueError: If the input is incorrectly formatted

    Returns:
        str: The formatted input
    '''
    # Get list of 'words' included in the user input
    word_list: list[str] = re.sub(r'(?:[0-9]|[^\w])', ' ', input).split()

    # Validate for each distinct style if all word occurrences are allowed
    if style == 0:
        legal: list[str] = legal_math
    elif style == 1:
        legal = legal_graph
    elif style == 2:
        legal = legal_solve
    for word in word_list:
        if not word in legal:
            raise ValueError(f'Illegal argument: {word}')

    # Replace operators with python notation / functions
    input = input.replace('mod', '%')
    if style == 0:
        input = input.replace('sin', 'cmath.sin')
        input = input.replace('cos', 'cmath.cos')
        input = input.replace('tan', 'cmath.tan')
        input = input.replace('floor(', 'wrap_fn(\'math.floor\',')
        input = input.replace('ceil(', 'wrap_fn(\'math.ceil\',')
        input = input.replace('round(', 'wrap_fn(\'round\',')
        input = input.replace('sqrt', 'cmath.sqrt')
        input = input.replace('log', 'cmath.log')
        input = input.replace('sum', 'calcsum')
        input = input.replace('product', 'calcproduct')
    elif style == 1:
        input = input.replace('sin', 'np.sin')
        input = input.replace('cos', 'np.cos')
        input = input.replace('tan', 'np.tan')
        input = input.replace('round', 'np.round_')
        input = input.replace('floor', 'np.floor')
        input = input.replace('ceil', 'np.ceil')
        input = input.replace('sqrt', 'np.sqrt')
        input = input.replace('log', 'np.log')
    elif style == 2:
        input = input.replace('pi', str(pi))
        input = input.replace('alpha', str(alpha))
        input = input.replace('delta', str(delta))
        input = input.replace('theta', str(theta))
        input = input.replace('tau', str(tau))
        input = input.replace('phi', str(phi))
        input = input.replace('gamma', str(gamma))
        input = input.replace('lambda', str(lambda_var))
        input = input.replace('psi', str(psi))
        input = input.replace('rho', str(rho))
        input = input.replace('e', str(e))
        input = input.replace('i', 'I')
        input = input.replace('sIn', 'sin')
    input = input.replace(')(', ')*(')
    input = input.replace('^', '**')
    input = input.replace('lambda', 'lambda_var')

    # Prepend and append multiplication symbols to any strings 
    # matching the pattern depending on the style
    if style == 0:
        pattern: str = pattern_math
    elif style == 1:
        pattern = pattern_graph
    elif style == 2:
        pattern = pattern_solve
    input = re.sub(pattern, '*(', input)
    input = re.sub(r'\)(?=[0-9a-zA-Z])', ')*', input)

    # For any indices where a number is followed by a letter or vice versa,
    # Insert a multiplication symbol
    indices: list[int] = []
    for index, char in enumerate(input):
        if len(input) > index+1 and re.search(r'[\d]', char):
            next_char = input[index+1]
            if re.search(r'[a-z]', next_char):
                indices.append(index)
        if len(input) > index+1 and re.search(r'[a-zA-Z]', char):
            next_char = input[index+1]
            if re.search(r'[\d]', next_char):
                indices.append(index)
    for index in reversed(indices):
        input = input[:index+1] + '*' + input[index+1:]
    
    # If using the math command, validate formatting for sum and product functions
    if style == 0:
        indices = []
        for index, char in enumerate(input):
            if char == 'x':
                check = 0
                j: int = index
                parentheses = 0
                while j >= 0:
                    if input[j] == ',':
                        indices.append(j)
                        check += 1
                        break
                    elif input[j] == '(':
                        parentheses += 1
                    elif input[j] == ')':
                        parentheses -= 1
                    j -= 1
                j = index
                while len(input) > j:
                    if input[j] == '(':
                        parentheses += 1
                    elif input[j] == ')' and parentheses == 0:
                        indices.append(j-1)
                        check += 1
                        break
                    elif input[j] == ')':
                        parentheses -= 1
                    j += 1
                if not check == 2:
                    raise ValueError(f'Incorrectly formatted function f(x) at index {index}')
        for index in sorted(indices, reverse=True):
            input = input[:index+1] + '\'' + input[index+1:]
    
    # If using the math command, format factorials
    if style == 0:
        # Get all indices of occurrences of '!'
        indices = [index for index, char in enumerate(input) if char == '!']
        # Construct a dictionary mapping each index of an occurrence of '!' to its depth level of parentheses.
        # E.g. (10!)! would have depth 1 for the first occurrence, and depth 0 for the second.
        parentheses_depth_dict: dict[int, int] = {}
        for index in indices:
            parentheses_depth_dict[index] = parentheses_depth(input, index)
        
        # Loop through occurrences of '!' in descending order of parentheses depth level
        processed: list[int] = []
        for occurrence in sorted([index for index in range(len(indices))], key=lambda index: parentheses_depth_dict[indices[index]], reverse=True):
            # In each iteration an occurrence is removed, 
            # hence for each occurrence we need to subtract 1 for each processed earlier occurrence
            occurrence -= len([p for p in processed if p < occurrence])

            # Get the current index of this occurrence
            index: int = index_of_occurrence(input, '!', occurrence+1)

            # Replace f(x)! by math.factorial(f(x))
            # First replace the '!' by ')'
            input = input[:index] + ')' + input[index+1:]
            # Then find the index to insert 'math.factorial('
            parentheses = 0
            for c_i, char in enumerate(reversed(input[:index])):
                if char == ')':
                    parentheses += 1
                    continue
                elif char == '(':
                    parentheses -= 1
                    continue
                # If this is the first character of the string, then insert here
                if index - c_i == 1:
                    input = 'math.factorial(' + input
                    break
                # If this is a number and the next (i.e. preceding) character is not a number, insert here
                elif parentheses == 0 and re.search(r'[\d]', char):
                    if not re.search(r'[\d]', input[index-c_i-2]):
                        input = input[:index-c_i-1] + 'math.factorial(' + input[index-c_i-1:]
                        break
                # If this character is not a number and not a letter, decimal point, or underscore, insert here
                elif parentheses == 0 and not re.search(r'[a-zA-Z]|\.|_', char):
                    input = input[:index-c_i-1] + 'math.factorial(' + input[index-c_i-1:]
                    break
                

            processed.append(occurrence)

    return input

def parentheses_depth(input: str, index: int) -> int:
    '''
    Get the depth level of parentheses at the given index in the input string.

    Args:
        input (str): The input string
        index (int): The parenthesis index

    Returns:
        int: The depth level of the parenthesis at the given index of the input string
    '''
    depth = 0
    for char in input[:index]:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
    return depth

def index_of_occurrence(input: str, sub: str, n: int) -> int:
    '''
    Gets the index of the nth occurrence of the given substring in the input string.

    Args:
        input (str): The input string
        sub (str): The substring to search for
        n (int): The occurrence to find

    Returns:
        int: The index of the nth occurrence of the given substring in the input string
    '''
    occurrence: int = 0
    index: int = 0
    while occurrence < n:
        index = input[index+(1 if index > 0 else 0):].index(sub) + index + (1 if index > 0 else 0)
        occurrence += 1
    return index

def format_output(result: numeric | str) -> str:
    '''
    Format the output result as a mathematical expression.

    Args:
        result (numeric | str): The result to format

    Returns:
        str: The formatted result
    '''
    if isinstance(result, complex):
        if cmath.isclose(result.imag, 0, abs_tol=1*10**(-11)):
            result = result.real
        elif cmath.isclose(result.real, 0, abs_tol=1*10**(-11)):
            result = complex(0, result.imag)
    if isinstance(result, complex):
        if (math.isinf(result.real) and result.real > 0) and (math.isinf(result.imag) and result.imag > 0):
            result = '∞ + ∞i'
        elif (math.isinf(result.real) and result.real < 0) and (math.isinf(result.imag) and result.imag < 0):
            result = '-∞ - ∞i'
        elif (math.isinf(result.real) and result.real > 0) and (math.isinf(result.imag) and result.imag < 0):
            result = '∞ - ∞i'
        elif (math.isinf(result.real) and result.real < 0) and (math.isinf(result.imag) and result.imag > 0):
            result = '-∞ + ∞i'
        elif (math.isinf(result.real) and result.real > 0):
            result = f'∞ + {result.imag}i'
        elif (math.isinf(result.imag) and result.imag > 0):
            result = f'{result.real} + ∞i'
        elif (math.isinf(result.real) and result.real < 0):
            result = f'-∞ + {result.imag}i'
        elif (math.isinf(result.imag) and result.imag < 0):
            result = f'{result.real} - ∞i'
    if isinstance(result, float):
        if math.isinf(result) and result > 0:
            result = '∞'
        elif math.isinf(result) and result < 0:
            result = '-∞'
        elif result.is_integer():
            result = round(result)
    result = str(result)

    result = result.replace('j', 'i')
    result = result.replace('(', '')
    result = result.replace(')', '')

    result = result.replace('pi', 'π')
    result = result.replace('i', '𝑖')
    result = result.replace('exp', 'EXP')
    result = result.replace('x', '𝓍')
    result = result.replace('EXP', 'exp')
    result = result.replace('sqrt', '√')

    return result

def prettify_input(input: str) -> str:
    '''
    Make the user-input pretty when showing it in the result.

    Args:
        input (str): The input string to prettify

    Returns:
        str: The prettified input string
    '''
    input = input.replace('pi', 'π')
    input = input.replace('alpha', 'α')
    input = input.replace('delta', 'δ')
    input = input.replace('theta', 'θ')
    input = input.replace('tau', 'τ')
    input = input.replace('phi', 'φ')
    input = input.replace('gamma', 'γ')
    input = input.replace('lambda', 'λ')
    input = input.replace('psi', 'ψ')
    input = input.replace('rho', 'ρ')
    input = input.replace('inf', '∞')
    input = input.replace('sum', 'Σ')
    input = input.replace('product', '∏')
    input = input.replace('sqrt', '√')
    input = input.replace('x', '𝓍')
    input = input.replace('i', '𝑖')
    input = input.replace('e', '𝑒')
    input = input.replace('s𝑖n', 'sin')
    return input

def solve_for_x(input: str, val: DictProxy) -> None:
    '''
    Reformat input and solve the resulting mathematical equality for x.
    Output(s) are added to the values of dictionary 'val'.

    Args:
        input (str): The input string
        val (DictProxy): The dictionary proxy to write the solutions to

    Raises:
        ValueError: If the input string is incorrectly formatted
    '''
    if not 'x' in input:
        raise ValueError('No variable \'x\' in equation')
    inputs: list[str] = input.split('=')
    if len(inputs) == 1:
        raise ValueError('No equality sign \'=\' in equation')
    elif len(inputs) > 2:
        raise ValueError('More than one equality sign \'=\' in equation')
    input = f'Eq({inputs[0]}, {inputs[1]})'
    equation: Any = sympy.sympify(input)
    solutions: list = sympy.solve(equation)
    for s_i, solution in enumerate(solutions):
        val[s_i] = solution

def plot_func(x: np.ndarray, input: str, val: DictProxy) -> None:
    '''
    Plot the given function 'input' for given range x.
    Output(s) are added to the values of dictionary 'val'.

    Args:
        x (np.ndarray): The array of x values to plot
        input (str): The input string
        val (DictProxy): The dictionary proxy to write the results to
    '''
    def func(x: numeric) -> numeric:
        return eval(input)
    for x_i in x:
        try:
            val[x_i] = func(x_i)
        except Exception as e:
            val[x_i] = e
            return