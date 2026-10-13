"""NUBAN (Nigeria Uniform Bank Account Number) helpers.

A NUBAN is 10 digits: a 9-digit serial number + 1 check digit.
The check digit is computed over the 3-digit bank code + the 9-digit serial.
"""
WEIGHTS = (3, 7, 3, 3, 7, 3, 3, 7, 3, 3, 7, 3)


def check_digit(bank_code: str, serial: str) -> int:
    if not (bank_code.isdigit() and len(bank_code) == 3):
        raise ValueError("bank_code must be 3 digits")
    if not (serial.isdigit() and len(serial) == 9):
        raise ValueError("serial must be 9 digits")
    digits = bank_code + serial
    total = sum(int(d) * w for d, w in zip(digits, WEIGHTS))
    return (10 - total % 10) % 10


def generate(bank_code: str, serial: int) -> str:
    """Build a full 10-digit NUBAN from a bank code and an integer serial."""
    s = str(serial).zfill(9)
    return s + str(check_digit(bank_code, s))


def is_valid(bank_code: str, account_number: str) -> bool:
    if not (account_number.isdigit() and len(account_number) == 10):
        return False
    return check_digit(bank_code, account_number[:9]) == int(account_number[9])
