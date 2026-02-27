import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import battery_health


class TestParsing(unittest.TestCase):
    def test_extract_first_int(self):
        self.assertEqual(battery_health._extract_first_int("53,210 mWh"), 53210)
        self.assertEqual(battery_health._extract_first_int("no digits"), 0)

    def test_parse_battery_report_html(self):
        sample_html = """
        <html><body>
        <table>
            <tr><th>NAME</th><th>DESIGN CAPACITY</th><th>FULL CHARGE CAPACITY</th></tr>
            <tr><td>GENERIC_BATTERY</td><td>53,210 mWh</td><td>49,500 mWh</td></tr>
        </table>
        </body></html>
        """

        batteries = battery_health._parse_battery_report_html(sample_html)
        self.assertEqual(len(batteries), 1)
        self.assertEqual(batteries[0]["device_id"], "GENERIC_BATTERY")
        self.assertEqual(batteries[0]["design_capacity_mwh"], 53210)
        self.assertEqual(batteries[0]["full_charge_capacity_mwh"], 49500)
        self.assertAlmostEqual(batteries[0]["health_percent"], 93.03, places=2)

    def test_parse_battery_report_prefers_installed_batteries_table(self):
        sample_html = """
        <html><body>
        <h2>Installed batteries</h2>
        <table>
            <tr>
                <th>NAME</th><th>MANUFACTURER</th><th>DESIGN CAPACITY</th>
                <th>FULL CHARGE CAPACITY</th><th>CYCLE COUNT</th>
            </tr>
            <tr>
                <td>GENERIC_BATTERY</td><td>GENERIC_VENDOR</td><td>50,000 mWh</td><td>45,000 mWh</td><td>120</td>
            </tr>
        </table>

        <h2>Battery capacity history</h2>
        <table>
            <tr><th>PERIOD</th><th>FULL CHARGE CAPACITY</th><th>DESIGN CAPACITY</th></tr>
            <tr><td>2026-02-26</td><td>35,948 mWh</td><td>64,448 mWh</td></tr>
        </table>
        </body></html>
        """

        batteries = battery_health._parse_battery_report_html(sample_html)
        self.assertEqual(len(batteries), 1)
        self.assertEqual(batteries[0]["device_id"], "GENERIC_BATTERY")
        self.assertEqual(batteries[0]["design_capacity_mwh"], 50000)
        self.assertEqual(batteries[0]["full_charge_capacity_mwh"], 45000)
        self.assertAlmostEqual(batteries[0]["health_percent"], 90.0, places=2)
        self.assertEqual(batteries[0]["cycle_count"], 120)

    def test_parse_battery_report_key_value_installed_table(self):
        sample_html = """
        <html><body>
        <h2>Installed batteries</h2>
        <table>
            <tr><td>NAME</td><td>GENERIC_BATTERY</td></tr>
            <tr><td>MANUFACTURER</td><td>GENERIC_VENDOR</td></tr>
            <tr><td>DESIGN CAPACITY</td><td>50,000 mWh</td></tr>
            <tr><td>FULL CHARGE CAPACITY</td><td>45,000 mWh</td></tr>
            <tr><td>CYCLE COUNT</td><td>120</td></tr>
        </table>
        </body></html>
        """

        batteries = battery_health._parse_battery_report_html(sample_html)
        self.assertEqual(len(batteries), 1)
        self.assertEqual(batteries[0]["device_id"], "GENERIC_BATTERY")
        self.assertEqual(batteries[0]["design_capacity_mwh"], 50000)
        self.assertEqual(batteries[0]["full_charge_capacity_mwh"], 45000)
        self.assertAlmostEqual(batteries[0]["health_percent"], 90.0, places=2)
        self.assertEqual(batteries[0]["cycle_count"], 120)

    def test_parse_battery_report_two_column_locale_fallback(self):
        sample_html = """
        <html><body>
        <table>
            <tr><td>NOMBRE</td><td>GENERIC_BATTERY</td></tr>
            <tr><td>CAPACIDAD DE DISENO</td><td>50,000 mWh</td></tr>
            <tr><td>CAPACIDAD DE CARGA COMPLETA</td><td>45,000 mWh</td></tr>
            <tr><td>CICLOS</td><td>120</td></tr>
        </table>
        </body></html>
        """
        batteries = battery_health._parse_battery_report_html(sample_html)
        self.assertEqual(len(batteries), 1)
        self.assertEqual(batteries[0]["device_id"], "GENERIC_BATTERY")
        self.assertEqual(batteries[0]["design_capacity_mwh"], 50000)
        self.assertEqual(batteries[0]["full_charge_capacity_mwh"], 45000)
        self.assertAlmostEqual(batteries[0]["health_percent"], 90.0, places=2)


class TestWindowsEnrichment(unittest.TestCase):
    def test_enrich_windows_batteries_adds_current_capacity_and_voltage(self):
        batteries = [
            {
                "device_id": "GENERIC_BATTERY",
                "design_capacity_mwh": 50000,
                "full_charge_capacity_mwh": 45000,
                "health_percent": 90.0,
            }
        ]

        runtime_rows = [{"device_id": "GENERIC_BATTERY", "charge_percent": 50, "voltage_mv": 11500}]
        with patch("battery_health._get_windows_runtime_details", return_value=runtime_rows):
            enriched = battery_health._enrich_windows_batteries(batteries)

        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0]["current_capacity_mwh"], 22500.0)
        self.assertEqual(enriched[0]["voltage_mv"], 11500)


class TestFileDecoding(unittest.TestCase):
    def test_read_text_with_fallbacks_utf16(self):
        text = "<html><table><tr><td>DESIGN CAPACITY</td><td>50000 mWh</td></tr></table></html>"
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as temp_file:
            path = Path(temp_file.name)
        try:
            path.write_bytes(text.encode("utf-16"))
            decoded = battery_health._read_text_with_fallbacks(path)
            self.assertIn("DESIGN CAPACITY", decoded)
        finally:
            if path.exists():
                path.unlink()


class TestWindowsPowercfgCleanup(unittest.TestCase):
    def test_temp_report_deleted_on_success(self):
        expected_path = None

        def fake_run(*args, **kwargs):
            self.assertIsNotNone(expected_path)
            Path(expected_path).write_text(
                """
                <table>
                    <tr><th>NAME</th><th>DESIGN CAPACITY</th><th>FULL CHARGE CAPACITY</th></tr>
                    <tr><td>BATTERY</td><td>50000 mWh</td><td>45000 mWh</td></tr>
                </table>
                """,
                encoding="utf-8",
            )

        with tempfile.NamedTemporaryFile(prefix="bh_test_", suffix=".html", delete=False) as temp_file:
            expected_path = temp_file.name

        with patch("battery_health.tempfile.NamedTemporaryFile") as mock_tmp, patch(
            "battery_health.subprocess.run", side_effect=fake_run
        ):
            mock_tmp.return_value.__enter__.return_value.name = expected_path
            mock_tmp.return_value.__exit__.return_value = False

            result = battery_health._get_battery_info_windows_powercfg()

        self.assertEqual(len(result), 1)
        self.assertFalse(Path(expected_path).exists(), "Temporary report file should be deleted")

    def test_temp_report_deleted_on_failure(self):
        expected_path = None

        with tempfile.NamedTemporaryFile(prefix="bh_test_", suffix=".html", delete=False) as temp_file:
            expected_path = temp_file.name

        with patch("battery_health.tempfile.NamedTemporaryFile") as mock_tmp, patch(
            "battery_health.subprocess.run", side_effect=FileNotFoundError
        ):
            mock_tmp.return_value.__enter__.return_value.name = expected_path
            mock_tmp.return_value.__exit__.return_value = False

            result = battery_health._get_battery_info_windows_powercfg()

        self.assertEqual(result, [])
        self.assertFalse(Path(expected_path).exists(), "Temporary report file should be deleted")


if __name__ == "__main__":
    unittest.main()
