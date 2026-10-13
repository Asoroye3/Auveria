import unittest
from apps.accounts import nuban


class NubanTests(unittest.TestCase):
    def test_generated_numbers_validate(self):
        for serial in (1, 42, 999_999_999, 123_456_789):
            acct = nuban.generate("044", serial)
            self.assertEqual(len(acct), 10)
            self.assertTrue(nuban.is_valid("044", acct))

    def test_wrong_check_digit_rejected(self):
        acct = nuban.generate("044", 69000003)
        bad = acct[:9] + str((int(acct[9]) + 1) % 10)
        self.assertFalse(nuban.is_valid("044", bad))

    def test_rejects_malformed_input(self):
        self.assertFalse(nuban.is_valid("044", "12345"))
        self.assertFalse(nuban.is_valid("044", "abcdefghij"))
        with self.assertRaises(ValueError):
            nuban.generate("44", 1)


if __name__ == "__main__":
    unittest.main()
