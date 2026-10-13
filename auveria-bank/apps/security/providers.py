"""SMS providers: the seam between Auveria and an SMS gateway.

Production would plug in a real gateway (Termii, Africa's Talking, Twilio...)
by writing one class with a send(phone, message) method and pointing
settings.SMS_PROVIDER at it.
"""


class ConsoleSMSProvider:
    """Dev 'SMS gateway': prints the message in the runserver terminal."""

    def send(self, phone: str, message: str) -> None:
        print(f"\n[SMS to {phone}] {message}\n", flush=True)


class LocMemSMSProvider:
    """Collects messages in memory so tests can read them."""

    outbox = []

    def send(self, phone: str, message: str) -> None:
        LocMemSMSProvider.outbox.append((phone, message))
