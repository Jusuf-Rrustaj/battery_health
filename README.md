# Battery Health

Simple cross-platform battery health checker for Windows, Linux, and macOS.

## What This Script Shows
- Battery identifier (model/system battery id)
- Design capacity
- Full charge capacity
- Health percentage
- Optional values when available: current capacity, voltage, cycle count

## Requirements
- Python 3.8+ installed
- No third-party packages required

This project uses only Python's standard library.

## Beginner Setup
1. Open a terminal in this project folder:
   `path\to\battery_health`
2. Confirm Python is installed:
   ```bash
   python --version
   ```
3. Run the script:
   ```bash
   python battery_health.py
   ```
4. (Optional) Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

## Example Output
```text
Battery: <identifier>
  Design Capacity:      <value> mWh
  Full Charge Capacity: <value> mWh
  Health:               <value>%
  Current Capacity:     <value> mWh
  Voltage:              <value> mV
  Cycle Count:          <value>
```

## Running Tests
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## Platform Notes
- Windows:
  - Uses `powercfg /batteryreport` as the primary source.
  - Temporary report files are deleted automatically after parsing.
  - Optionally enriches output with live battery fields from `Win32_Battery` when Windows exposes them.
  - Falls back to `wmic` only on older systems where available.
- Linux:
  - Reads battery info from `/sys/class/power_supply/BAT*`.
- macOS:
  - Reads battery info using `ioreg`.

## Troubleshooting
- `No battery detected or unable to read battery information.`:
  - Confirm the machine actually has a battery (desktops usually do not).
  - On Windows, run `powercfg /batteryreport` manually to confirm battery data is available.
  - Make sure Python is running with permission to execute system battery commands.
- `python` not recognized:
  - Install Python from https://www.python.org/downloads/ and ensure "Add Python to PATH" is enabled.

## Safety
- The script does not install anything or modify system settings.
- Any temporary files generated for report parsing are safely cleaned up.
