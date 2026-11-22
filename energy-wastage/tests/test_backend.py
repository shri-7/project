import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1] / "backend"
PROJECT = BACKEND.parent
SAMPLE_DATA = PROJECT / "data" / "sample_household_power_consumption.csv"
sys.path.insert(0, str(BACKEND))

import app as backend


def test_create_sequences_shape():
    data = np.arange(120).reshape(120, 1)
    sequences = backend.create_sequences(data, 96)
    assert sequences.shape == (25, 96, 1)


def test_preprocess_resamples_and_splits(tmp_path):
    timestamps = pd.date_range("2024-01-01", periods=12000, freq="1min")
    frame = pd.DataFrame({
        "Date": timestamps.strftime("%d/%m/%Y"),
        "Time": timestamps.strftime("%H:%M:%S"),
        "Global_active_power": np.linspace(0.2, 2.0, len(timestamps)),
        "Global_reactive_power": np.linspace(0.1, 0.4, len(timestamps)),
        "Voltage": np.linspace(230, 240, len(timestamps)),
        "Global_intensity": np.linspace(1, 10, len(timestamps)),
        "Sub_metering_1": 0,
        "Sub_metering_2": 0,
        "Sub_metering_3": 0,
    })
    path = tmp_path / "household_power_consumption.txt"
    frame.to_csv(path, sep=";", index=False)

    resampled, train, validation = backend.load_and_preprocess(path, 250000)

    assert len(resampled) >= 400
    assert len(train) + len(validation) < len(resampled)


def test_sample_file_has_labeled_anomaly_events():
    data, _, _ = backend.load_and_preprocess(SAMPLE_DATA, 250000)

    assert len(data) == 21 * 24 * 4
    assert data["Anomaly"].sum() == 48
    assert data.loc[data["Anomaly"] == 1, "Global_active_power"].min() == 3.5


def test_labeled_metrics_calculate_precision_recall_and_f1():
    metrics = backend.calculate_labeled_metrics(
        np.array([1, 1, 0, 0]),
        np.array([1, 0, 1, 0]),
    )

    assert metrics == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "evaluated_windows": 4,
        "positive_windows": 2,
        "true_positives": 1,
        "false_positives": 1,
        "false_negatives": 1,
    }


def test_create_sequences_requires_enough_data():
    with pytest.raises(ValueError, match="Need more than 4 records"):
        backend.create_sequences(np.arange(4).reshape(-1, 1), 4)


def test_safe_extract_rejects_path_traversal(tmp_path):
    import zipfile

    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")

    with pytest.raises(ValueError, match="outside the dataset directory"):
        backend.safe_extract_zip(archive_path, tmp_path / "data")


def test_upload_accepts_sample_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "DATA_DIR", tmp_path)

    with TestClient(backend.app) as client:
        with SAMPLE_DATA.open("rb") as sample:
            response = client.post(
                "/api/upload",
                files={"file": (SAMPLE_DATA.name, sample, "text/csv")},
            )

    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"
    assert (tmp_path / "household_power_consumption.txt").exists()


def test_health_and_dashboard_routes():
    with TestClient(backend.app) as client:
        health = client.get("/api/health")
        dashboard = client.get("/")

    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert dashboard.status_code == 200
    assert "WattWatch" in dashboard.text


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("tensorflow"),
    reason="TensorFlow is required for the LSTM end-to-end test",
)
def test_lstm_pipeline_reports_test_accuracy(monkeypatch, tmp_path):
    monkeypatch.setattr(backend, "download_dataset", lambda: SAMPLE_DATA)
    monkeypatch.setattr(backend, "MODEL_DIR", tmp_path)
    result = backend.run_analysis(
        backend.AnalysisRequest(threshold_percentile=99, epochs=3, sequence_length=96)
    )

    assert result["status"] == "completed"
    assert result["test_metrics"] is not None
    assert result["test_metrics"]["evaluated_windows"] > 0
    assert 0 <= result["test_metrics"]["precision"] <= 1
    assert 0 <= result["test_metrics"]["recall"] <= 1
    assert 0 <= result["test_metrics"]["f1"] <= 1
    assert result["test_metrics"]["f1"] >= 0.7
    assert result["interval_count"] == len(result["anomaly_mask"])
