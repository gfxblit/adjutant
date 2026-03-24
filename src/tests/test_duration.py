import unittest
from datetime import datetime, timezone, timedelta
from adjutant.engine import format_duration


class TestDurationFormatting(unittest.TestCase):
    def test_format_duration_seconds(self):
        now = datetime.now(timezone.utc)
        iso_date = (now - timedelta(seconds=30)).isoformat()
        self.assertEqual(format_duration(iso_date), "30s")

    def test_format_duration_minutes(self):
        now = datetime.now(timezone.utc)
        iso_date = (now - timedelta(minutes=5, seconds=30)).isoformat()
        self.assertEqual(format_duration(iso_date), "5m")

    def test_format_duration_hours(self):
        now = datetime.now(timezone.utc)
        iso_date = (now - timedelta(hours=2, minutes=15)).isoformat()
        self.assertEqual(format_duration(iso_date), "2h15m")

    def test_format_duration_days(self):
        now = datetime.now(timezone.utc)
        iso_date = (now - timedelta(days=3, hours=4)).isoformat()
        self.assertEqual(format_duration(iso_date), "3d4h")

    def test_format_duration_future(self):
        now = datetime.now(timezone.utc)
        iso_date = (now + timedelta(seconds=30)).isoformat()
        self.assertEqual(format_duration(iso_date), "0s")

    def test_format_duration_invalid(self):
        self.assertEqual(format_duration("not-a-date"), "???")
        self.assertEqual(format_duration(None), "???")

    def test_format_duration_z_replacement(self):
        # Test that it handles 'Z' suffix correctly (mimicking bd output)
        iso_date = "2026-03-22T12:00:00Z"
        # Since we compare against 'now', this might be a large duration.
        # Just ensure it doesn't crash and returns something other than ???
        duration = format_duration(iso_date)
        self.assertNotEqual(duration, "???")


if __name__ == "__main__":
    unittest.main()
