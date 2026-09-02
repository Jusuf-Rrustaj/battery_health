# Battery Health

Simple cross-platform battery health checker for Windows, Linux, and macOS.

## What This Script Shows
- Battery identifier (model/system battery id)
- Design capacity
- Full charge capacity
- Health percentage
- Optional values when available: current capacity, voltage, cycle count
- Estimated runtime on a full charge (Windows only)

## Estimated Runtime on a Full Charge (Windows)
Answers "how long does this laptop actually last from 100% to 0%?" rather than
"how much time is left right now", which Windows already shows in the taskbar.

The figures come from the battery report's own life estimates, which Windows
builds from the drains it has observed on the machine:

- **Typical, all-time** - average runtime on a full charge since the OS was installed.
- **Typical, recent** - average over the last few reported periods. A degrading
  battery makes the all-time number optimistic, so this tracks its current state
  more closely.
- **If battery were new** - the same usage projected onto the battery's design
  capacity, i.e. what the laptop delivered when new.

Useful when buying a used laptop: the gap between "typical" and "if battery were
new" shows what the wear actually costs in hours, independent of the seller's claims.

Caveats worth knowing:
- These reflect *the previous owner's* workload. Light browsing and heavy
  compiling produce very different numbers on identical hardware.
- A machine that has rarely run on battery gives Windows little to observe, so
  the section is omitted when no usable estimates exist.
- The section is system-wide, so it is printed once even on dual-battery laptops.

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

Estimated Runtime on a Full Charge (100% -> 0%)
  Typical, all-time:    2h 30m
  Typical, recent:      2h 23m  (last 8 periods)
  If battery were new:  4h 23m
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
  - Full-charge runtime estimates are read from the same report, so they need no
    extra command and work on both Windows 10 and 11. Report headings are
    localized, so the estimate tables are located by position rather than by text.
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
