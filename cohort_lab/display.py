"""Shared exhibit formatting; displayed rounding never changes analytical values."""
from decimal import Decimal, ROUND_HALF_UP


def retention_label(share: float) -> str:
    """Whole percent, with .5 rounded up consistently in report and slides."""
    return str(Decimal(str(float(share) * 100)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
