from .models import Account

CASH_VAULT_NAME = "Cash Vault"


def open_account(customer) -> Account:
    """Open a savings account for a verified customer."""
    return Account.objects.create(customer=customer, owner_name=customer.full_name)


def get_cash_account() -> Account:
    """The bank's cash vault. Deposits debit it, withdrawals credit it.

    Convention: balance = credits - debits. Cash coming in debits the vault, so
    the vault runs negative by exactly the amount customers hold. Because every
    transaction balances, the sum of ALL account balances is always zero.
    """
    vault = Account.objects.filter(is_system=True, owner_name=CASH_VAULT_NAME).first()
    return vault or Account.objects.create(is_system=True, owner_name=CASH_VAULT_NAME)
