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


def _life_estimates_report(include_estimates=True):
    """
    Mirrors the shape of a real powercfg report: a usage history table whose rows
    are structurally identical to the battery life estimates rows, followed by the
    per-period estimates table and the single-row "since OS install" table.
    """
    usage_history = """
    <h2>Usage history</h2>
    <table>
        <thead>
            <tr><td> </td><td colspan="2">BATTERY DURATION</td><td class="colBreak"> </td><td colspan="3">AC DURATION</td></tr>
            <tr><td>PERIOD</td><td>ACTIVE</td><td>CONNECTED STANDBY</td><td class="colBreak"> </td><td>ACTIVE</td><td>CONNECTED STANDBY</td></tr>
        </thead>
        <tr><td class="dateTime">2026-04-06 - 2026-04-13</td><td class="hms">6:52:40</td><td class="nullValue">-</td><td class="colBreak"> </td><td class="hms">53:51:51</td><td class="nullValue">-</td></tr>
        <tr><td class="dateTime">2026-04-13 - 2026-04-20</td><td class="hms">8:23:36</td><td class="nullValue">-</td><td class="colBreak"> </td><td class="hms">62:24:24</td><td class="nullValue">-</td></tr>
    </table>
    """

    if not include_estimates:
        return f"<html><body>{usage_history}</body></html>"

    estimates = """
    <h2>Battery life estimates</h2>
    <table>
        <thead>
            <tr><td> </td><td colspan="2">AT FULL CHARGE</td><td class="colBreak"> </td><td colspan="2">AT DESIGN CAPACITY</td></tr>
            <tr><td>PERIOD</td><td>ACTIVE</td><td>CONNECTED STANDBY</td><td class="colBreak"> </td><td>ACTIVE</td><td>CONNECTED STANDBY</td></tr>
        </thead>
        <tr><td class="dateTime">2026-08-24</td><td class="nullValue">-</td><td class="nullValue">-</td><td class="colBreak"> </td><td class="nullValue">-</td><td class="nullValue">-</td></tr>
        <tr><td class="dateTime">2026-08-25</td><td class="hms">2:00:00</td><td class="nullValue">-</td><td class="colBreak"> </td><td class="hms">3:30:00</td><td class="nullValue">-</td></tr>
        <tr><td class="dateTime">2026-08-26</td><td class="hms">3:00:00</td><td class="nullValue">-</td><td class="colBreak"> </td><td class="hms">5:00:00</td><td class="nullValue">-</td></tr>
    </table>
    <table>
        <tr><td>Since OS install</td><td class="hms">2:29:47</td><td class="nullValue">-</td><td class="colBreak"> </td><td class="hms">4:23:11</td><td class="nullValue">-</td></tr>
    </table>
    """
    return f"<html><body>{usage_history}{estimates}</body></html>"


class TestBatteryLifeEstimates(unittest.TestCase):
    def test_parse_duration_to_hours(self):
        self.assertAlmostEqual(battery_health._parse_duration_to_hours("2:29:47"), 2.4963889, places=6)
        self.assertAlmostEqual(battery_health._parse_duration_to_hours("1:02:00:00"), 26.0, places=6)
        self.assertIsNone(battery_health._parse_duration_to_hours("-"))
        self.assertIsNone(battery_health._parse_duration_to_hours(""))
        self.assertIsNone(battery_health._parse_duration_to_hours("0:00:00"))
        self.assertIsNone(battery_health._parse_duration_to_hours("53,210 mWh"))

    def test_parses_since_os_install_estimates(self):
        estimates = battery_health._parse_battery_life_estimates(_life_estimates_report())

        self.assertIsNotNone(estimates)
        self.assertAlmostEqual(estimates["full_charge_hours"], 2.4963889, places=6)
        self.assertAlmostEqual(estimates["design_capacity_hours"], 4.3863889, places=6)

    def test_ignores_lookalike_usage_history_table(self):
        # Usage history rows have the same shape but mean hours spent on battery,
        # not runtime on a full charge, so they must never feed the estimates.
        estimates = battery_health._parse_battery_life_estimates(_life_estimates_report())

        self.assertAlmostEqual(estimates["recent_full_charge_hours"], 2.5, places=6)
        self.assertEqual(estimates["recent_period_count"], 2)

    def test_returns_none_without_estimates_section(self):
        report = _life_estimates_report(include_estimates=False)
        self.assertIsNone(battery_health._parse_battery_life_estimates(report))

    def test_returns_none_when_never_run_on_battery(self):
        report = """
        <html><body>
        <table>
            <tr><td>Since OS install</td><td class="nullValue">-</td><td class="nullValue">-</td><td class="colBreak"> </td><td class="nullValue">-</td><td class="nullValue">-</td></tr>
        </table>
        </body></html>
        """
        self.assertIsNone(battery_health._parse_battery_life_estimates(report))

    def test_format_hours(self):
        self.assertEqual(battery_health._format_hours(2.4963889), "2h 30m")
        self.assertEqual(battery_health._format_hours(4.0), "4h 00m")


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
