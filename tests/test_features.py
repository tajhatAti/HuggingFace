from __future__ import annotations

import unittest

from code_assistant.features import (
    FEATURE_COUNT,
    FEATURE_GROUPS,
    render_feature_catalog,
)


class FeatureCatalogTests(unittest.TestCase):
    def test_catalog_has_at_least_one_hundred_unique_real_capabilities(self):
        features = [feature for _, group in FEATURE_GROUPS for feature in group]
        self.assertGreaterEqual(FEATURE_COUNT, 100)
        self.assertEqual(FEATURE_COUNT, len(features))
        self.assertEqual(len(features), len(set(features)))

    def test_renderer_numbers_every_capability(self):
        rendered = render_feature_catalog()
        self.assertIn(f"## {FEATURE_COUNT}+ production capabilities", rendered)
        self.assertIn("**001**", rendered)
        self.assertIn(f"**{FEATURE_COUNT:03d}**", rendered)


if __name__ == "__main__":
    unittest.main()
