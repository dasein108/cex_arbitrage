from exchanges.structs.common import Side


def get_minimal_step(precision: int) -> float:
    return 10**-precision

def count_decimal_places(number):
    """Count the number of decimal places."""
    str_number = str(number)
    if '.' in str_number:
        return len(str_number.split('.')[1])
    return 0


def get_decrease_vector(side: Side, tick: int = 1) -> int:
    """Get decrease vector based on side, up for selling, down for buying."""
    return -tick if side == Side.BUY else tick


def calculate_weighted_price(price1: float, quantity1: float, price2: float, quantity2: float) -> tuple[float, float]:
    previous_filled = quantity1
    previous_cost = price1 * previous_filled if previous_filled > 1e-8 else 0.0

    # New order cost = price2 * quantity2
    new_order_cost = price2 * quantity2

    # Update total filled quantity
    new_filled_quantity = quantity1 + quantity2

    # Calculate new weighted average price
    total_cost = previous_cost + new_order_cost
    if new_filled_quantity > 0:
        new_avg_price = total_cost / new_filled_quantity
    else:
        new_avg_price = 0.0

    return new_filled_quantity, new_avg_price