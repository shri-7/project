import csv
import math
from datetime import datetime, timedelta
from pathlib import Path


OUTPUT = Path(__file__).resolve().parents[1] / "data" / "sample_household_power_consumption.csv"
START = datetime(2024, 1, 1)
INTERVALS = 21 * 24 * 4
ANOMALY_RANGES = ((1752, 1768), (1850, 1866), (1940, 1956))


def create_sample() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output, delimiter=";")
        writer.writerow([
            "Date",
            "Time",
            "Global_active_power",
            "Global_reactive_power",
            "Voltage",
            "Global_intensity",
            "Sub_metering_1",
            "Sub_metering_2",
            "Sub_metering_3",
            "Anomaly",
        ])
        for index in range(INTERVALS):
            timestamp = START + timedelta(minutes=15 * index)
            hour = timestamp.hour + timestamp.minute / 60
            power = 0.7 + 0.18 * math.sin(2 * math.pi * (hour - 7) / 24)
            power += 0.04 * math.sin(2 * math.pi * timestamp.day / 7)
            anomaly = int(any(start <= index < end for start, end in ANOMALY_RANGES))
            if anomaly:
                power = 3.5
            writer.writerow([
                timestamp.strftime("%d/%m/%Y"),
                timestamp.strftime("%H:%M:%S"),
                f"{power:.4f}",
                f"{0.12 + power * 0.08:.4f}",
                f"{235 + 2 * math.sin(2 * math.pi * hour / 24):.3f}",
                f"{power * 4.35:.4f}",
                f"{power * 1.2:.4f}",
                f"{power * 0.8:.4f}",
                f"{power * 0.5:.4f}",
                anomaly,
            ])


if __name__ == "__main__":
    create_sample()
