from exchanges.structs.common import Side


def get_minimal_step(precision: int) -> float:
    return 10**-precision


def get_decrease_vector(side: Side, tick: int = 1) -> int:
    """Get decrease vector based on side, up for selling, down for buying."""
    return -tick if side == Side.BUY else tick