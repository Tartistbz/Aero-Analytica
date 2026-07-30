import unittest

from src.ui.components import (
    count_selected_fields,
    filter_field_messages,
    remove_selected_field,
    sanitize_field_mapping,
    set_message_fields,
)


class FieldSelectionTests(unittest.TestCase):
    def setUp(self):
        self.all_fields = {
            "ATT": ["Roll", "Pitch", "Yaw"],
            "GPS": ["Alt", "Spd", "NSats"],
            "battery_status": ["voltage_v", "current_a"],
        }

    def test_sanitize_removes_unknown_and_duplicate_fields(self):
        mapping = {
            "ATT": ["Roll", "Missing", "Roll", "Pitch"],
            "UNKNOWN": ["Value"],
            "GPS": "Alt",
        }

        sanitized = sanitize_field_mapping(mapping, self.all_fields)

        self.assertEqual(sanitized, {"ATT": ["Roll", "Pitch"]})

    def test_set_message_fields_preserves_other_messages(self):
        mapping = {"ATT": ["Roll"], "GPS": ["Alt"]}

        updated = set_message_fields(
            mapping, "ATT", ["Pitch", "Yaw"], self.all_fields
        )

        self.assertEqual(
            updated,
            {"ATT": ["Pitch", "Yaw"], "GPS": ["Alt"]},
        )
        self.assertEqual(mapping, {"ATT": ["Roll"], "GPS": ["Alt"]})

    def test_empty_message_selection_removes_message(self):
        updated = set_message_fields(
            {"ATT": ["Roll"], "GPS": ["Alt"]},
            "ATT",
            [],
            self.all_fields,
        )

        self.assertEqual(updated, {"GPS": ["Alt"]})

    def test_remove_last_field_drops_message(self):
        updated = remove_selected_field(
            {"ATT": ["Roll"], "GPS": ["Alt", "Spd"]},
            "ATT",
            "Roll",
        )

        self.assertEqual(updated, {"GPS": ["Alt", "Spd"]})

    def test_filter_matches_message_or_field_case_insensitively(self):
        self.assertEqual(filter_field_messages(self.all_fields, "gPs"), ["GPS"])
        self.assertEqual(
            filter_field_messages(self.all_fields, "VOLTAGE"),
            ["battery_status"],
        )
        self.assertEqual(
            filter_field_messages(self.all_fields, ""),
            ["ATT", "battery_status", "GPS"],
        )

    def test_count_selected_fields(self):
        self.assertEqual(
            count_selected_fields({"ATT": ["Roll"], "GPS": ["Alt", "Spd"]}),
            3,
        )


if __name__ == "__main__":
    unittest.main()
