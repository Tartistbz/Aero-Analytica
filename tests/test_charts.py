import unittest

import pandas as pd

from src.ui.charts import get_plot_columns, resolve_visible_columns


class ChartColumnTests(unittest.TestCase):
    def setUp(self):
        self.dataframe = pd.DataFrame(
            {
                "timestamp": [0.0, 1.0],
                "GPS_Alt": [10.0, 11.0],
                "mode": ["AUTO", "AUTO"],
                "ATT_Roll": [1.0, 2.0],
            }
        )

    def test_get_plot_columns_excludes_timestamp_and_mode(self):
        self.assertEqual(
            get_plot_columns(self.dataframe),
            ["GPS_Alt", "ATT_Roll"],
        )

    def test_visible_columns_preserve_dataframe_order(self):
        self.assertEqual(
            resolve_visible_columns(
                self.dataframe,
                ["ATT_Roll", "missing", "GPS_Alt"],
            ),
            ["GPS_Alt", "ATT_Roll"],
        )

    def test_unspecified_visibility_shows_every_plot_column(self):
        self.assertEqual(
            resolve_visible_columns(self.dataframe),
            ["GPS_Alt", "ATT_Roll"],
        )

    def test_empty_visibility_hides_all_plot_columns(self):
        self.assertEqual(resolve_visible_columns(self.dataframe, []), [])


if __name__ == "__main__":
    unittest.main()
