from __future__ import annotations

import unittest

from src.storage.transaction import _resolve_entity_name


class TransactionTerminologyResolutionTest(unittest.TestCase):
    def test_shudi_aliases_resolve_to_dihuang(self) -> None:
        self.assertEqual(_resolve_entity_name("熟地"), "地黄")
        self.assertEqual(_resolve_entity_name("熟地黄"), "地黄")

    def test_common_processed_herb_alias_resolves_to_canonical_name(self) -> None:
        self.assertEqual(_resolve_entity_name("炙甘草"), "甘草")

    def test_unknown_term_is_preserved(self) -> None:
        self.assertEqual(_resolve_entity_name("未知术语"), "未知术语")

    def test_surrounding_whitespace_is_ignored(self) -> None:
        self.assertEqual(_resolve_entity_name("  熟地  "), "地黄")


if __name__ == "__main__":
    unittest.main()
