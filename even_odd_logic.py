def generate_even_odd(start: int, end: int, is_even: bool) -> str:
    """
    Generates a comma-separated string of even or odd numbers within a given range.
    """
    numbers_list = []
    
    # Ensure start is always less than or equal to end for the range to work
    step = 1 if start <= end else -1
    range_end = end + 1 if start <= end else end - 1
    
    for number in range(start, range_end, step):
        if is_even and number % 2 == 0:
            numbers_list.append(str(number))
        elif not is_even and number % 2 != 0:
            numbers_list.append(str(number))
            
    return ", ".join(numbers_list)
