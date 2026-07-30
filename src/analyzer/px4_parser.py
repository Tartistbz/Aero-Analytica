from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from pyulog import ULog

from .parser_base import ParserBase


class PX4Parser(ParserBase):
    """Discover and extract fields from PX4 ULog files."""

    # These values are stable across the PX4 versions used by common flight logs.
    # Unknown values keep their numeric identity instead of being mislabeled.
    NAV_STATE_NAMES = {
        0: "MANUAL",
        1: "ALTCTL",
        2: "POSCTL",
        3: "AUTO_MISSION",
        4: "AUTO_LOITER",
        5: "AUTO_RTL",
    }

    def __init__(self, file_path):
        super().__init__(file_path)
        self._ulog = None
        self._datasets = None

    def _load_ulog(self):
        if self._ulog is None:
            self._ulog = ULog(str(self.file_path))
        return self._ulog

    @staticmethod
    def _dataset_key(dataset):
        name = str(dataset.name)
        multi_id = int(getattr(dataset, "multi_id", 0) or 0)
        return name if multi_id == 0 else f"{name}[{multi_id}]"

    def _get_datasets(self):
        if self._datasets is None:
            self._datasets = {
                self._dataset_key(dataset): dataset
                for dataset in self._load_ulog().data_list
            }
        return self._datasets

    def list_all_fields(self) -> dict:
        """Return every timestamped topic and its actual ULog data fields."""
        fields_map = {}
        for dataset_key, dataset in self._get_datasets().items():
            data = getattr(dataset, "data", {})
            if not isinstance(data, Mapping) or "timestamp" not in data:
                continue
            fields = [str(field) for field in data if field != "timestamp"]
            if fields:
                fields_map[dataset_key] = fields
        return fields_map

    @staticmethod
    def _timestamp_index(values):
        timestamps = np.asarray(values)
        if timestamps.ndim != 1 or timestamps.size == 0:
            return None
        try:
            timestamp_seconds = timestamps.astype(np.float64) / 1e6
        except (TypeError, ValueError):
            return None
        return timestamp_seconds

    def _dataset_frame(self, dataset_key, dataset, requested_fields):
        if isinstance(requested_fields, (str, bytes)) or not isinstance(
            requested_fields, Sequence
        ):
            return pd.DataFrame()

        data = getattr(dataset, "data", {})
        if not isinstance(data, Mapping) or "timestamp" not in data:
            return pd.DataFrame()

        timestamps = self._timestamp_index(data["timestamp"])
        if timestamps is None:
            return pd.DataFrame()

        columns = {}
        seen_fields = set()
        for field in requested_fields:
            if not isinstance(field, str) or field in seen_fields:
                continue
            seen_fields.add(field)
            if field == "timestamp" or field not in data:
                continue

            values = np.asarray(data[field])
            if values.ndim != 1 or len(values) != len(timestamps):
                continue
            columns[f"{dataset_key}_{field}"] = values

        if not columns:
            return pd.DataFrame()

        frame = pd.DataFrame(columns, index=timestamps)
        frame.index.name = "timestamp"
        frame = frame[np.isfinite(frame.index)]
        frame = frame[~frame.index.duplicated(keep="last")]
        return frame.sort_index()

    @classmethod
    def _format_nav_state(cls, value):
        try:
            nav_state = int(value)
        except (TypeError, ValueError, OverflowError):
            return "UNKNOWN"
        return cls.NAV_STATE_NAMES.get(nav_state, f"NAV_STATE {nav_state}")

    def _mode_frame(self):
        dataset = self._get_datasets().get("vehicle_status")
        if dataset is None:
            return pd.DataFrame()

        data = getattr(dataset, "data", {})
        if not isinstance(data, Mapping) or "nav_state" not in data:
            return pd.DataFrame()
        timestamps = self._timestamp_index(data.get("timestamp", []))
        nav_states = np.asarray(data["nav_state"])
        if (
            timestamps is None
            or nav_states.ndim != 1
            or len(nav_states) != len(timestamps)
        ):
            return pd.DataFrame()

        frame = pd.DataFrame(
            {"mode": [self._format_nav_state(value) for value in nav_states]},
            index=timestamps,
        )
        frame.index.name = "timestamp"
        frame = frame[np.isfinite(frame.index)]
        frame = frame[~frame.index.duplicated(keep="last")]
        return frame.sort_index()

    def get_custom_dataframe(self, field_mapping: dict) -> pd.DataFrame:
        """Extract selected topics on a unified, forward-filled time axis."""
        if not isinstance(field_mapping, Mapping) or not field_mapping:
            return pd.DataFrame()

        datasets = self._get_datasets()
        frames = []
        for dataset_key, requested_fields in field_mapping.items():
            dataset = datasets.get(dataset_key)
            if dataset is None:
                continue
            frame = self._dataset_frame(
                dataset_key,
                dataset,
                requested_fields,
            )
            if not frame.empty:
                frames.append(frame)

        if not frames:
            return pd.DataFrame()

        mode_frame = self._mode_frame()
        if not mode_frame.empty:
            frames.append(mode_frame)

        combined = pd.concat(frames, axis=1, join="outer")
        combined = combined.sort_index(kind="mergesort").ffill()
        combined.index.name = "timestamp"
        return combined.reset_index()
