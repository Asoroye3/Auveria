import unittest

from apps.kyc.providers import MockIdentityProvider


class MockProviderTests(unittest.TestCase):
    def setUp(self):
        self.p = MockIdentityProvider()

    def test_same_first_four_digits_same_person(self):
        a = self.p.lookup_bvn("22211111111")
        b = self.p.lookup_nin("22219999999")
        self.assertEqual(a, b)

    def test_different_first_four_digits_different_person(self):
        self.assertNotEqual(self.p.lookup_bvn("22211111111"), self.p.lookup_nin("22229999999"))

    def test_numbers_ending_0000_not_found(self):
        self.assertIsNone(self.p.lookup_bvn("22210000000"))
        self.assertIsNone(self.p.lookup_nin("22210000000"))


if __name__ == "__main__":
    unittest.main()
