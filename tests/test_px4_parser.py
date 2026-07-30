import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.analyzer.px4_parser import PX4Parser


class FakeDataset:
    def __init__(self, name, data, multi_id=0):
        self.name = name
        self.multi_id = multi_id
        self.data = data


class PX4ParserTests(unittest.TestCase):
    @staticmethod
    def _ulog(datasets):
        return SimpleNamespace(data_list=datasets)

    def test_list_all_fields_uses_data_keys_and_labels_instances(self):
        datasets = [
            FakeDataset(
                "sensor_gyro",
                {"timestamp": np.array([1_000_000]), "x": np.array([1.0])},
            ),
            FakeDataset(
                "sensor_gyro",
                {"timestamp": np.array([1_000_000]), "x": np.array([2.0])},
                multi_id=1,
            ),
        ]

        with patch(
            "src.analyzer.px4_parser.ULog",
            return_value=self._ulog(datasets),
        ):
            fields = PX4Parser("flight.ulg").list_all_fields()

        self.assertEqual(
            fields,
            {"sensor_gyro": ["x"], "sensor_gyro[1]": ["x"]},
        )

    def test_selected_topics_are_outer_aligned_and_modes_added(self):
        datasets = [
            FakeDataset(
                "vehicle_attitude",
                {
                    "timestamp": np.array([1_000_000, 3_000_000]),
                    "roll": np.array([0.1, 0.3]),
                },
            ),
            FakeDataset(
                "battery_status",
                {
                    "timestamp": np.array([2_000_000]),
                    "voltage_v": np.array([12.0]),
                },
            ),
            FakeDataset(
                "vehicle_status",
                {
                    "timestamp": np.array([1_500_000, 2_500_000]),
                    "nav_state": np.array([0, 3]),
                },
            ),
        ]

        with patch(
            "src.analyzer.px4_parser.ULog",
            return_value=self._ulog(datasets),
        ):
            frame = PX4Parser("flight.ulg").get_custom_dataframe(
                {
                    "vehicle_attitude": ["roll"],
                    "battery_status": ["voltage_v"],
                }
            )

        self.assertEqual(
            list(frame.columns),
            [
                "timestamp",
                "vehicle_attitude_roll",
                "battery_status_voltage_v",
                "mode",
            ],
        )
        self.assertEqual(frame["timestamp"].tolist(), [1.0, 1.5, 2.0, 2.5, 3.0])
        self.assertAlmostEqual(frame.iloc[-1]["vehicle_attitude_roll"], 0.3)
        self.assertAlmostEqual(frame.iloc[-1]["battery_status_voltage_v"], 12.0)
        self.assertEqual(frame.iloc[-1]["mode"], "AUTO_MISSION")

    def test_multi_instance_topic_can_be_extracted(self):
        datasets = [
            FakeDataset(
                "sensor_gyro",
                {"timestamp": np.array([1_000_000]), "x": np.array([1.0])},
            ),
            FakeDataset(
                "sensor_gyro",
                {"timestamp": np.array([2_000_000]), "x": np.array([2.0])},
                multi_id=1,
            ),
        ]

        with patch(
            "src.analyzer.px4_parser.ULog",
            return_value=self._ulog(datasets),
        ):
            frame = PX4Parser("flight.ulg").get_custom_dataframe(
                {"sensor_gyro[1]": ["x"]}
            )

        self.assertEqual(list(frame.columns), ["timestamp", "sensor_gyro[1]_x"])
        self.assertEqual(frame.to_dict("records"), [{"timestamp": 2.0, "sensor_gyro[1]_x": 2.0}])

    def test_repository_ulog_can_be_scanned_and_extracted(self):
        log_path = Path(__file__).parents[1] / "data" / "log_32_UnknownDate.ulg"
        if not log_path.exists():
            self.skipTest("repository PX4 fixture is not available")

        parser = PX4Parser(log_path)
        fields = parser.list_all_fields()
        frame = parser.get_custom_dataframe(
            {
                "vehicle_attitude": ["q[0]"],
                "battery_status": ["voltage_v"],
            }
        )

        self.assertGreaterEqual(len(fields), 70)
        self.assertIn("q[0]", fields["vehicle_attitude"])
        self.assertIn("voltage_v", fields["battery_status"])
        self.assertFalse(frame.empty)
        self.assertTrue(frame["timestamp"].is_monotonic_increasing)
        self.assertTrue(frame["vehicle_attitude_q[0]"].notna().any())
        self.assertTrue(frame["battery_status_voltage_v"].notna().any())
        self.assertIn("mode", frame.columns)


if __name__ == "__main__":
    unittest.main()
