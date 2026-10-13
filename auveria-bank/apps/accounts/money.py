def naira(kobo) -> str:
    """Format integer kobo as naira, e.g. 500000 -> ₦5,000.00. Money stays in kobo in the DB."""
    if kobo is None:
        return "No limit"
    sign = "-" if kobo < 0 else ""
    kobo = abs(kobo)
    return f"{sign}₦{kobo // 100:,}.{kobo % 100:02d}"


def ngn(kobo: int) -> str:
    """Plain-text amount for SMS (the naira sign isn't in the basic GSM character set)."""
    return f"NGN {kobo // 100:,}.{kobo % 100:02d}"
