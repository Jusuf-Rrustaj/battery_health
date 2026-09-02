#!/usr/bin/env python3
"""
Cross-platform battery health checker.
Displays design capacity, full charge capacity, and health percentage.
Works on Windows, Linux, and macOS.
"""

import html
import json
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def _safe_health(full_capacity, design_capacity):
    if not full_capacity or not design_capacity:
        return 0.0
    return round((full_capacity / design_capacity) * 100, 2)


def _extract_first_int(text):
    match = re.search(r"(\d[\d,]*)", text or "")
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def _read_text_with_fallbacks(path):
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-16", "utf-16-le", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _normalize_device_id(device_id):
    value = (device_id or "").upper()
    return re.sub(r"[^A-Z0-9]", "", value)


# ------------------------------------------------------------
# Windows implementation
# ------------------------------------------------------------
def _normalize_cell(cell_html):
    plain = re.sub(r"<[^>]+>", " ", cell_html)
    plain = html.unescape(plain)
    return " ".join(plain.split())


def _find_tables(report_html):
    return re.findall(r"<table[^>]*>(.*?)</table>", report_html, flags=re.IGNORECASE | re.DOTALL)


def _parse_table_rows(table_html):
    parsed_rows = []
    row_html_list = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL)
    for row_html in row_html_list:
        cell_html_list = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
        if not cell_html_list:
            continue
        parsed_rows.append([_normalize_cell(cell) for cell in cell_html_list])
    return parsed_rows


def _looks_like_date(text):
    value = text.strip()
    return bool(
        re.match(r"^\d{4}-\d{2}-\d{2}$", value)
        or re.match(r"^\d{4}-\d{2}-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}$", value)
    )


def _parse_battery_report_html(report_html):
    """
    Parse powercfg battery report HTML and return battery list.
    """
    def _parse_header_table(rows):
        headers_upper = [h.upper() for h in rows[0]]
        if "DESIGN CAPACITY" not in headers_upper or "FULL CHARGE CAPACITY" not in headers_upper:
            return []
        # Avoid "BATTERY CAPACITY HISTORY" table where "PERIOD" is the identifier.
        if "PERIOD" in headers_upper:
            return []

        name_idx = headers_upper.index("NAME") if "NAME" in headers_upper else 0
        design_idx = headers_upper.index("DESIGN CAPACITY")
        full_idx = headers_upper.index("FULL CHARGE CAPACITY")
        cycle_idx = headers_upper.index("CYCLE COUNT") if "CYCLE COUNT" in headers_upper else None

        batteries = []
        for row in rows[1:]:
            max_idx = max(full_idx, design_idx, name_idx)
            if len(row) <= max_idx:
                continue

            device_name = row[name_idx] if row[name_idx] else "BATTERY"
            design = _extract_first_int(row[design_idx])
            full = _extract_first_int(row[full_idx])
            if design <= 0:
                continue

            battery = {
                "device_id": device_name,
                "design_capacity_mwh": design,
                "full_charge_capacity_mwh": full,
                "health_percent": _safe_health(full, design),
            }

            if cycle_idx is not None and len(row) > cycle_idx:
                cycle_value = _extract_first_int(row[cycle_idx])
                if cycle_value > 0:
                    battery["cycle_count"] = cycle_value

            batteries.append(battery)

        return batteries

    def _parse_key_value_table(rows):
        kv = {}
        for row in rows:
            if len(row) < 2:
                continue
            key = row[0].strip().upper().rstrip(":")
            value = row[1].strip()
            if key:
                kv[key] = value

        # Typical installed-battery table in powercfg reports.
        design_text = kv.get("DESIGN CAPACITY", "")
        full_text = kv.get("FULL CHARGE CAPACITY", "")
        if not design_text or not full_text:
            return []

        design = _extract_first_int(design_text)
        full = _extract_first_int(full_text)
        if design <= 0:
            return []

        battery = {
            "device_id": kv.get("NAME", "BATTERY"),
            "design_capacity_mwh": design,
            "full_charge_capacity_mwh": full,
            "health_percent": _safe_health(full, design),
        }

        cycle_value = _extract_first_int(kv.get("CYCLE COUNT", ""))
        if cycle_value > 0:
            battery["cycle_count"] = cycle_value

        return [battery]

    def _parse_two_column_mwh_table(rows):
        # Locale-tolerant fallback: parse 2-column tables by values (mWh) rather than labels.
        if not rows or not all(len(row) >= 2 for row in rows):
            return []

        mwh_values = []
        device_name = None
        cycle_count = None

        for row in rows:
            left = row[0].strip()
            right = row[1].strip()
            right_upper = right.upper()

            if "MWH" in right_upper:
                mwh_values.append(_extract_first_int(right))
            elif cycle_count is None:
                maybe_cycle = _extract_first_int(right)
                if maybe_cycle > 0 and maybe_cycle < 100000:
                    cycle_count = maybe_cycle

            if not device_name and right and not _looks_like_date(right):
                if "MWH" not in right_upper and len(right) <= 64:
                    device_name = right

            if not device_name and left and not _looks_like_date(left):
                if "MWH" not in left.upper() and len(left) <= 64:
                    device_name = left

        if len(mwh_values) < 2:
            return []

        design = mwh_values[0]
        full = mwh_values[1]
        if design <= 0:
            return []

        battery = {
            "device_id": device_name or "BATTERY",
            "design_capacity_mwh": design,
            "full_charge_capacity_mwh": full,
            "health_percent": _safe_health(full, design),
        }
        if cycle_count and cycle_count > 0:
            battery["cycle_count"] = cycle_count
        return [battery]

    for table_html in _find_tables(report_html):
        rows = _parse_table_rows(table_html)
        if not rows:
            continue

        batteries = _parse_header_table(rows)
        if not batteries:
            batteries = _parse_key_value_table(rows)
        if not batteries:
            batteries = _parse_two_column_mwh_table(rows)
        if batteries:
            return batteries

    return []


# ------------------------------------------------------------
# Windows battery life estimates ("how long does a full charge last")
# ------------------------------------------------------------
_DURATION_RE = re.compile(r"^\d{1,5}(?::\d{2}){2,3}$")

# How many trailing report periods feed the "recent" average.
_RECENT_PERIOD_COUNT = 8


def _parse_duration_to_hours(duration_text):
    """
    Convert a powercfg duration cell ("2:29:47", or "1:02:29:47" when it spans
    days) into hours. Returns None for missing ("-") or unrecognized values.
    """
    value = (duration_text or "").strip()
    if not _DURATION_RE.match(value):
        return None

    parts = [int(part) for part in value.split(":")]
    if len(parts) == 4:
        days, hours, minutes, seconds = parts
    else:
        days = 0
        hours, minutes, seconds = parts

    total_hours = days * 24 + hours + minutes / 60.0 + seconds / 3600.0
    return total_hours if total_hours > 0 else None


def _split_life_estimate_row(cells):
    """
    Rows of the battery life estimates tables are laid out as:
        PERIOD | ACTIVE | CONNECTED STANDBY | <spacer> | ACTIVE | CONNECTED STANDBY
    The first ACTIVE column is the estimate at the battery's current full charge
    capacity, the second is the estimate at its design capacity. Only ACTIVE is
    used; connected standby measures sleep drain rather than usable runtime.

    Returns (full_charge_hours, design_capacity_hours); either may be None.
    """
    if len(cells) < 5:
        return None, None

    # The spacer column separates the two groups. It is the only truly empty
    # cell in a data row, because missing values are rendered as "-".
    spacer_idx = next((i for i in range(2, len(cells) - 1) if not cells[i]), None)
    design_idx = spacer_idx + 1 if spacer_idx is not None else 4
    if design_idx >= len(cells):
        return None, None

    return _parse_duration_to_hours(cells[1]), _parse_duration_to_hours(cells[design_idx])


def _average_recent_estimates(rows):
    """
    Average the trailing rows of the per-period estimates table. The since-install
    figure is diluted by history from when the pack was younger, so recent periods
    describe its current condition more closely.
    """
    period_hours = []
    for cells in rows:
        full_charge_hours, design_capacity_hours = _split_life_estimate_row(cells)
        if full_charge_hours is None:
            continue
        # Design capacity is never below full charge capacity, so the runtime at
        # design capacity cannot be the shorter of the two. A row saying otherwise
        # means this is not the estimates table.
        if design_capacity_hours is not None and design_capacity_hours < full_charge_hours:
            return {}
        period_hours.append(full_charge_hours)

    if not period_hours:
        return {}

    recent = period_hours[-_RECENT_PERIOD_COUNT:]
    return {
        "recent_full_charge_hours": sum(recent) / len(recent),
        "recent_period_count": len(recent),
    }


def _parse_battery_life_estimates(report_html):
    """
    Parse the "Battery life estimates" section of a powercfg battery report.

    These are Windows' own estimates of how long a *full* charge lasts based on
    the drains it has actually observed on this machine, so they answer "how long
    does this laptop run from 100% to 0%" rather than "how long is left right
    now". The figures cover the system as a whole, not an individual battery.

    Section headings are localized, so the tables are located structurally: the
    report ends with a single-row "since OS install" table, immediately preceded
    by the per-period table. Both have the same row shape as the unrelated usage
    history table, which is why position rather than shape is the anchor.

    Returns None when the report carries no usable estimates, for example on a
    machine that has never run on battery.
    """
    tables = [_parse_table_rows(table_html) for table_html in _find_tables(report_html)]

    for index in range(len(tables) - 1, -1, -1):
        rows = tables[index]
        if len(rows) != 1:
            continue

        full_charge_hours, design_capacity_hours = _split_life_estimate_row(rows[0])
        if full_charge_hours is None and design_capacity_hours is None:
            continue

        estimates = {
            "full_charge_hours": full_charge_hours,
            "design_capacity_hours": design_capacity_hours,
        }

        previous_rows = tables[index - 1] if index > 0 else []
        if len(previous_rows) > 1:
            estimates.update(_average_recent_estimates(previous_rows))

        return estimates

    return None


def _get_battery_info_windows_powercfg():
    """
    Query battery information on Windows via:
      powercfg /batteryreport /output <tempfile>
    The generated report file is always cleaned up.
    """
    report_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="battery_report_", suffix=".html", delete=False) as temp_file:
            report_path = Path(temp_file.name)

        cmd = ["powercfg", "/batteryreport", "/output", str(report_path)]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        report_html = _read_text_with_fallbacks(report_path)
        batteries = _parse_battery_report_html(report_html)

        estimates = _parse_battery_life_estimates(report_html)
        if estimates:
            for battery in batteries:
                battery["runtime_estimates"] = estimates

        return batteries
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []
    finally:
        if report_path and report_path.exists():
            try:
                report_path.unlink()
            except OSError:
                pass


def _get_battery_info_windows_wmic_fallback():
    """
    Legacy fallback for older Windows systems where WMIC is still available.
    """
    try:
        cmd = [
            "wmic",
            "path",
            "Win32_Battery",
            "get",
            "DeviceID,DesignedCapacity,FullChargeCapacity",
            "/format:csv",
        ]
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.PIPE)
        lines = [line for line in output.strip().splitlines() if line.strip()]
        if len(lines) < 2:
            return []

        batteries = []
        for line in lines[1:]:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                continue

            device = parts[1] or "BATTERY"
            design = _extract_first_int(parts[2])
            full = _extract_first_int(parts[3])
            if design <= 0:
                continue

            batteries.append(
                {
                    "device_id": device,
                    "design_capacity_mwh": design,
                    "full_charge_capacity_mwh": full,
                    "health_percent": _safe_health(full, design),
                }
            )

        return batteries
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def _get_windows_runtime_details():
    """
    Try to fetch current charge percentage and voltage from Win32_Battery.
    Returns a list of dicts:
      {
        "device_id": str,
        "charge_percent": int|None,
        "voltage_mv": int|None
      }
    """
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Battery | Select-Object DeviceID,EstimatedChargeRemaining,DesignVoltage | ConvertTo-Json -Compress",
        ]
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.PIPE).strip()
        if not output:
            return []

        parsed = json.loads(output)
        rows = parsed if isinstance(parsed, list) else [parsed]
        runtime_rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            runtime_rows.append(
                {
                    "device_id": str(row.get("DeviceID") or ""),
                    "charge_percent": _extract_first_int(str(row.get("EstimatedChargeRemaining") or "")),
                    "voltage_mv": _extract_first_int(str(row.get("DesignVoltage") or "")),
                }
            )
        return runtime_rows
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return []


def _enrich_windows_batteries(batteries):
    runtime_rows = _get_windows_runtime_details()
    if not batteries or not runtime_rows:
        return batteries

    by_id = {}
    for row in runtime_rows:
        norm_id = _normalize_device_id(row.get("device_id"))
        if norm_id:
            by_id[norm_id] = row

    for battery in batteries:
        runtime = None
        norm_bat_id = _normalize_device_id(battery.get("device_id"))
        if norm_bat_id:
            runtime = by_id.get(norm_bat_id)

        if runtime is None and len(runtime_rows) == 1:
            # Single-battery fallback when names don't match.
            runtime = runtime_rows[0]

        if runtime is None:
            continue

        charge_percent = runtime.get("charge_percent", 0)
        if 0 <= charge_percent <= 100 and "full_charge_capacity_mwh" in battery:
            battery["current_capacity_mwh"] = (battery["full_charge_capacity_mwh"] * charge_percent) / 100.0

        voltage_mv = runtime.get("voltage_mv", 0)
        if voltage_mv > 0:
            battery["voltage_mv"] = voltage_mv

    return batteries


def get_battery_info_windows():
    batteries = _get_battery_info_windows_powercfg()
    if batteries:
        return _enrich_windows_batteries(batteries)
    batteries = _get_battery_info_windows_wmic_fallback()
    if batteries:
        return _enrich_windows_batteries(batteries)
    return []


# ------------------------------------------------------------
# Linux implementation using sysfs
# ------------------------------------------------------------
def get_battery_info_linux():
    power_supply_path = Path("/sys/class/power_supply")
    if not power_supply_path.exists():
        return []

    batteries = []
    for bat_path in power_supply_path.glob("BAT*"):
        bat_name = bat_path.name
        try:
            full_path = bat_path / "energy_full"
            if not full_path.exists():
                full_path = bat_path / "charge_full"

            design_path = bat_path / "energy_full_design"
            if not design_path.exists():
                design_path = bat_path / "charge_full_design"

            if not full_path.exists() or not design_path.exists():
                continue

            full_raw = int(full_path.read_text().strip())
            design_raw = int(design_path.read_text().strip())

            full_mwh = full_raw / 1000.0
            design_mwh = design_raw / 1000.0

            bat_info = {
                "device_id": bat_name,
                "design_capacity_mwh": design_mwh,
                "full_charge_capacity_mwh": full_mwh,
                "health_percent": _safe_health(full_mwh, design_mwh),
            }

            current_path = bat_path / "energy_now"
            if not current_path.exists():
                current_path = bat_path / "charge_now"
            if current_path.exists():
                current_raw = int(current_path.read_text().strip())
                bat_info["current_capacity_mwh"] = current_raw / 1000.0

            voltage_path = bat_path / "voltage_now"
            if voltage_path.exists():
                voltage_uv = int(voltage_path.read_text().strip())
                bat_info["voltage_mv"] = voltage_uv / 1000.0

            cycle_path = bat_path / "cycle_count"
            if cycle_path.exists():
                bat_info["cycle_count"] = int(cycle_path.read_text().strip())

            batteries.append(bat_info)
        except (FileNotFoundError, ValueError, PermissionError):
            continue

    return batteries


# ------------------------------------------------------------
# macOS implementation using ioreg
# ------------------------------------------------------------
def get_battery_info_macos():
    try:
        cmd = ["ioreg", "-l", "-w0"]
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.PIPE)

        design_cap = None
        max_cap = None
        voltage = None
        cycle_count = None
        device_name = "InternalBattery"

        for line in output.splitlines():
            m = re.search(r'"DesignCapacity"\s*=\s*(\d+)', line)
            if m:
                design_cap = int(m.group(1))
            m = re.search(r'"MaxCapacity"\s*=\s*(\d+)', line)
            if m:
                max_cap = int(m.group(1))
            m = re.search(r'"Voltage"\s*=\s*(\d+)', line)
            if m:
                voltage = int(m.group(1))
            m = re.search(r'"CycleCount"\s*=\s*(\d+)', line)
            if m:
                cycle_count = int(m.group(1))
            m = re.search(r'"DeviceName"\s*=\s*"([^"]+)"', line)
            if m:
                device_name = m.group(1)

        if design_cap is None or max_cap is None or design_cap <= 0:
            return []

        bat_info = {
            "device_id": device_name,
            "design_capacity_mah": design_cap,
            "max_capacity_mah": max_cap,
            "health_percent": _safe_health(max_cap, design_cap),
        }
        if voltage is not None:
            bat_info["voltage_mv"] = voltage
        if cycle_count is not None:
            bat_info["cycle_count"] = cycle_count
        return [bat_info]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


# ------------------------------------------------------------
# Main dispatcher
# ------------------------------------------------------------
def _format_hours(hours):
    total_minutes = int(round(hours * 60))
    return f"{total_minutes // 60}h {total_minutes % 60:02d}m"


def _print_runtime_estimates(estimates):
    print("Estimated Runtime on a Full Charge (100% -> 0%)")

    full_charge_hours = estimates.get("full_charge_hours")
    if full_charge_hours:
        print(f"  Typical, all-time:    {_format_hours(full_charge_hours)}")

    recent_hours = estimates.get("recent_full_charge_hours")
    if recent_hours:
        period_count = estimates.get("recent_period_count", 0)
        print(f"  Typical, recent:      {_format_hours(recent_hours)}  (last {period_count} periods)")

    design_capacity_hours = estimates.get("design_capacity_hours")
    if design_capacity_hours:
        print(f"  If battery were new:  {_format_hours(design_capacity_hours)}")

    print()
    print("  Based on drains Windows actually observed on this machine, so it")
    print("  reflects how this laptop has really been used, not a benchmark.")
    print()


def main():
    system = platform.system()

    if system == "Windows":
        batteries = get_battery_info_windows()
    elif system == "Linux":
        batteries = get_battery_info_linux()
    elif system == "Darwin":
        batteries = get_battery_info_macos()
    else:
        print(f"Unsupported OS: {system}", file=sys.stderr)
        return 1

    if not batteries:
        print("No battery detected or unable to read battery information.")
        return 1

    for bat in batteries:
        print(f"Battery: {bat['device_id']}")
        if "design_capacity_mwh" in bat:
            print(f"  Design Capacity:      {bat['design_capacity_mwh']:.0f} mWh")
            print(f"  Full Charge Capacity: {bat['full_charge_capacity_mwh']:.0f} mWh")
        elif "design_capacity_mah" in bat:
            print(f"  Design Capacity:      {bat['design_capacity_mah']} mAh")
            print(f"  Max Capacity:         {bat['max_capacity_mah']} mAh")

        print(f"  Health:               {bat['health_percent']:.1f}%")

        if "current_capacity_mwh" in bat:
            print(f"  Current Capacity:     {bat['current_capacity_mwh']:.0f} mWh")
        if "voltage_mv" in bat:
            print(f"  Voltage:              {bat['voltage_mv']:.0f} mV")
        if "cycle_count" in bat:
            print(f"  Cycle Count:          {int(bat['cycle_count'])}")
        print()

    # System-wide rather than per battery, so it is printed once after the list.
    estimates = next((bat["runtime_estimates"] for bat in batteries if "runtime_estimates" in bat), None)
    if estimates:
        _print_runtime_estimates(estimates)

    return 0


if __name__ == "__main__":
    exit_code = main()
    if getattr(sys, "frozen", False):
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
    sys.exit(exit_code)
