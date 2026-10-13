"""Identity providers: the seam between Auveria and BVN/NIN data sources.

Production would call NIBSS (BVN) and NIMC (NIN) through a licensed
aggregator. For this portfolio build we ship a deterministic mock.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol


@dataclass(frozen=True)
class IdentityRecord:
    full_name: str
    date_of_birth: date


class IdentityProvider(Protocol):
    def lookup_bvn(self, bvn: str) -> Optional[IdentityRecord]: ...
    def lookup_nin(self, nin: str) -> Optional[IdentityRecord]: ...


_NAMES = [
    "Adaeze Okafor",
    "Tunde Bakare",
    "Hauwa Ibrahim",
    "Emeka Nwosu",
    "Folake Adeyemi",
    "Musa Danjuma",
]


class MockIdentityProvider:
    """Fake NIBSS/NIMC.

    Rules (handy for demos and tests):
    - Numbers ending in "0000" are "not found".
    - Otherwise the person is derived from the FIRST 4 digits, so a BVN and
      a NIN that share their first 4 digits belong to the same person.
    """

    def _person(self, number: str) -> Optional[IdentityRecord]:
        if number.endswith("0000"):
            return None
        key = int(number[:4])
        return IdentityRecord(
            full_name=_NAMES[key % len(_NAMES)],
            date_of_birth=date(1990 + key % 10, 1 + key % 12, 1 + key % 28),
        )

    def lookup_bvn(self, bvn: str) -> Optional[IdentityRecord]:
        return self._person(bvn)

    def lookup_nin(self, nin: str) -> Optional[IdentityRecord]:
        return self._person(nin)
