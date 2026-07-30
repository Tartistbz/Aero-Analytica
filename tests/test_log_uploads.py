import tempfile
import unittest
from pathlib import Path

from src.log_uploads import store_uploaded_log


class LogUploadTests(unittest.TestCase):
    def test_upload_is_stored_by_content_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(
                store_uploaded_log(
                    "flight.ulg",
                    b"ulg-content",
                    root=Path(temp_dir),
                )
            )

            self.assertEqual(path.suffix, ".ulg")
            self.assertEqual(len(path.stem), 64)
            self.assertEqual(path.read_bytes(), b"ulg-content")

    def test_existing_content_is_reused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = Path(store_uploaded_log("flight.ulg", b"same", root=root))
            first.chmod(0o444)

            second = Path(store_uploaded_log("flight.ulg", b"same", root=root))

            self.assertEqual(second, first)
            self.assertEqual(second.read_bytes(), b"same")

    def test_same_name_with_different_content_uses_different_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = store_uploaded_log("flight.ulg", b"first", root=root)
            second = store_uploaded_log("flight.ulg", b"second", root=root)

            self.assertNotEqual(first, second)

    def test_invalid_extension_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "\.bin 和 \.ulg"):
                store_uploaded_log(
                    "../flight.txt",
                    b"content",
                    root=Path(temp_dir),
                )


if __name__ == "__main__":
    unittest.main()
