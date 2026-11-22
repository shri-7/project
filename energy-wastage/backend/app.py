import asyncio
import threading
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sklearn.metrics import precision_score, recall_score, f1_score
from sklearn.preprocessing import MinMaxScaler

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
MODEL_DIR = APP_DIR / "models"
FRONTEND_DIR = APP_DIR / "frontend"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

UCI_URLS = (
    "https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip",
    "https://raw.githubusercontent.com/saurabhg9/UCI-datasets/master/individual+household+electric+power+consumption.zip",
)

app = FastAPI(
    title="Hidden Electrical Energy Wastage Detector",
    version="1.0.0",
    description="LSTM Autoencoder dashboard for 15-minute household electricity analysis.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    threshold_percentile: int = Field(default=99, ge=95, le=99)
    epochs: int = Field(default=10, ge=1, le=100)
    sequence_length: int = Field(default=96, ge=24, le=288)
    data_rows: int = Field(default=250000, ge=5000, le=250000)


class JobState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.status = "idle"
            self.progress = 0
            self.message = "Waiting to start"
            self.error = None
            self.results = None


state = JobState()


def update_status(status: str, progress: int, message: str) -> None:
    with state.lock:
        state.status = status
        state.progress = progress
        state.message = message


def set_error(message: str) -> None:
    with state.lock:
        state.status = "failed"
        state.progress = 100
        state.error = message
        state.message = "Analysis failed"


def download_dataset() -> Path:
    zip_path = DATA_DIR / "household_power_consumption.zip"
    txt_path = DATA_DIR / "household_power_consumption.txt"
    if txt_path.exists():
        return txt_path
    if zip_path.exists():
        zip_path.unlink()

    last_error = None
    for url in UCI_URLS:
        try:
            urllib.request.urlretrieve(url, zip_path)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise RuntimeError(f"Dataset download failed: {last_error}")

    safe_extract_zip(zip_path, DATA_DIR)
    candidates = list(DATA_DIR.glob("**/household_power_consumption.txt"))
    if not candidates:
        raise RuntimeError("Downloaded archive did not contain household_power_consumption.txt")
    return candidates[0]


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            resolved_path = (destination / member.filename).resolve()
            if resolved_path != destination and destination not in resolved_path.parents:
                raise ValueError("ZIP contains a path outside the dataset directory")
        archive.extractall(destination)


def load_and_preprocess(file_path: Path, data_rows: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(file_path, sep=None, engine="python", nrows=data_rows)
    raw.columns = raw.columns.str.strip()
    required = {
        "Date",
        "Time",
        "Global_active_power",
        "Global_reactive_power",
        "Voltage",
        "Global_intensity",
        "Sub_metering_1",
        "Sub_metering_2",
        "Sub_metering_3",
    }
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {', '.join(sorted(missing))}")
    raw["Datetime"] = pd.to_datetime(
        raw["Date"].astype(str).str.strip() + " " + raw["Time"].astype(str).str.strip(),
        dayfirst=True,
        errors="coerce",
    )
    raw = raw.dropna(subset=["Datetime"])
    numeric_cols = [
        "Global_active_power",
        "Global_reactive_power",
        "Voltage",
        "Global_intensity",
        "Sub_metering_1",
        "Sub_metering_2",
        "Sub_metering_3",
    ]
    for column in numeric_cols:
        raw[column] = pd.to_numeric(raw[column].astype(str).str.strip(), errors="coerce")
    raw[numeric_cols] = raw[numeric_cols].interpolate(method="linear").ffill().bfill()
    if raw[numeric_cols].isna().any().any():
        raise ValueError("Dataset has no valid numeric readings after cleaning")

    label_column = next(
        (column for column in ("Anomaly", "anomaly", "is_anomaly", "label", "Label") if column in raw.columns),
        None,
    )
    if label_column:
        labels = raw[label_column].astype(str).str.strip().str.lower()
        raw["Anomaly"] = labels.isin({"1", "true", "yes", "anomaly"}).astype(int)

    raw.set_index("Datetime", inplace=True)
    resampled = raw[numeric_cols].resample("15min").mean().interpolate(method="linear")
    if label_column:
        resampled["Anomaly"] = raw["Anomaly"].resample("15min").max().fillna(0).astype(int)
    resampled = resampled.dropna()

    total = len(resampled)
    train_count = int(total * 0.70)
    val_count = int(total * 0.15)
    train_end = train_count
    val_end = train_count + val_count
    if min(train_end, val_end - train_end, total - val_end) < 2:
        raise ValueError("Dataset must contain at least 2 resampled intervals in each chronological split")
    return resampled, resampled.iloc[:train_count], resampled.iloc[train_count : train_count + val_count]


def create_sequences(data: np.ndarray, sequence_length: int) -> np.ndarray:
    if len(data) <= sequence_length:
        raise ValueError(f"Need more than {sequence_length} records to create sequences")
    return np.asarray([data[index : index + sequence_length] for index in range(len(data) - sequence_length + 1)])


def calculate_labeled_metrics(ground_truth: np.ndarray, predictions: np.ndarray) -> dict:
    ground_truth = np.asarray(ground_truth, dtype=bool)
    predictions = np.asarray(predictions, dtype=bool)
    if ground_truth.shape != predictions.shape:
        raise ValueError("Ground truth and predictions must have the same shape")
    return {
        "precision": round(float(precision_score(ground_truth, predictions, zero_division=0)), 4),
        "recall": round(float(recall_score(ground_truth, predictions, zero_division=0)), 4),
        "f1": round(float(f1_score(ground_truth, predictions, zero_division=0)), 4),
        "evaluated_windows": int(ground_truth.size),
        "positive_windows": int(np.sum(ground_truth)),
        "true_positives": int(np.sum(ground_truth & predictions)),
        "false_positives": int(np.sum(~ground_truth & predictions)),
        "false_negatives": int(np.sum(ground_truth & ~predictions)),
    }


def train_lstm_autoencoder(train_sequences: np.ndarray, val_sequences: np.ndarray, sequence_length: int, epochs: int):
    try:
        import tensorflow as tf
        from tensorflow.keras.callbacks import EarlyStopping
        from tensorflow.keras.layers import Dense, Input, LSTM, RepeatVector, TimeDistributed
        from tensorflow.keras.models import Sequential
    except ImportError as exc:
        raise RuntimeError("TensorFlow is not installed") from exc

    tf.random.set_seed(42)
    model = Sequential([
        Input(shape=(sequence_length, 1)),
        LSTM(32, activation="relu", return_sequences=False, name="Encoder_LSTM"),
        RepeatVector(sequence_length, name="Latent_Bridge"),
        LSTM(32, activation="relu", return_sequences=True, name="Decoder_LSTM"),
        TimeDistributed(Dense(1), name="Output_Layer"),
    ])
    model.compile(optimizer="adam", loss="mse")
    early_stopping = EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)
    history = model.fit(
        train_sequences,
        train_sequences,
        epochs=epochs,
        batch_size=128,
        validation_data=(val_sequences, val_sequences),
        callbacks=[early_stopping],
        verbose=0,
    )
    model_path = MODEL_DIR / "lstm_autoencoder_wastage_model.keras"
    model.save(model_path)
    return model, history.history


def run_analysis(request: AnalysisRequest) -> dict:
    update_status("running", 10, "Loading and validating the dataset")
    file_path = download_dataset()

    update_status("running", 20, "Cleaning values and resampling to 15-minute intervals")
    resampled, train_df, val_df = load_and_preprocess(file_path, request.data_rows)
    test_start = int(len(resampled) * 0.85)
    test_df = resampled.iloc[test_start:]

    update_status("running", 35, "Scaling training data and creating 24-hour sequences")
    scaler = MinMaxScaler()
    scaler.fit(train_df[["Global_active_power"]])
    train_scaled = scaler.transform(train_df[["Global_active_power"]])
    val_scaled = scaler.transform(val_df[["Global_active_power"]])
    test_scaled = scaler.transform(test_df[["Global_active_power"]])
    train_sequences = create_sequences(train_scaled, request.sequence_length)
    val_sequences = create_sequences(val_scaled, request.sequence_length)
    test_sequences = create_sequences(test_scaled, request.sequence_length)

    update_status("running", 45, "Training the LSTM Autoencoder")
    model, history = train_lstm_autoencoder(
        train_sequences,
        val_sequences,
        request.sequence_length,
        request.epochs,
    )

    update_status("running", 75, "Detecting anomalous reconstruction windows")
    val_predictions = model.predict(val_sequences, verbose=0)
    test_predictions = model.predict(test_sequences, verbose=0)
    val_mae = np.mean(np.abs(val_sequences - val_predictions), axis=(1, 2))
    test_mae = np.mean(np.abs(test_sequences - test_predictions), axis=(1, 2))
    threshold = float(np.percentile(val_mae, request.threshold_percentile))
    anomaly_indices = np.where(test_mae > threshold)[0]

    test_actual_scaled = test_scaled[request.sequence_length - 1 :]
    test_reconstructed_scaled = test_predictions[:, -1, 0]
    count = min(len(test_actual_scaled), len(test_reconstructed_scaled))
    test_actual_scaled = test_actual_scaled[:count].reshape(-1, 1)
    test_reconstructed_scaled = test_reconstructed_scaled[:count].reshape(-1, 1)
    actual_kw = scaler.inverse_transform(test_actual_scaled).ravel()
    reconstructed_kw = scaler.inverse_transform(test_reconstructed_scaled).ravel()
    timeline_index = test_df.index[request.sequence_length - 1 : request.sequence_length - 1 + count]

    is_anomaly = np.zeros(count, dtype=bool)
    valid_indices = anomaly_indices[anomaly_indices < count]
    is_anomaly[valid_indices] = True
    labeled_metrics = None
    if "Anomaly" in test_df.columns:
        # A sequence is labeled anomalous if it contains any labeled anomaly.
        ground_truth = (
            pd.Series(test_df["Anomaly"].to_numpy())
            .rolling(window=request.sequence_length, min_periods=request.sequence_length)
            .max()
            .iloc[request.sequence_length - 1 :]
            .to_numpy(dtype=bool)[:count]
        )
        labeled_metrics = calculate_labeled_metrics(ground_truth, is_anomaly)
    positive_residual = actual_kw - reconstructed_kw
    wastage_candidates = (positive_residual > 0) & is_anomaly
    excess_kwh = np.where(wastage_candidates, positive_residual * 0.25, 0.0)
    total_wastage = float(np.sum(excess_kwh))

    test_series = pd.Series(actual_kw)
    rolling_mean = test_series.rolling(window=12, min_periods=1).mean()
    rolling_std = test_series.rolling(window=12, min_periods=1).std().fillna(0)
    statistical_anomalies = (test_series > rolling_mean + 2.5 * rolling_std).to_numpy()

    hourly = resampled.groupby(resampled.index.hour)["Global_active_power"].mean()
    weekly = resampled.groupby(resampled.index.dayofweek)["Global_active_power"].mean()
    distribution = actual_kw.tolist()

    update_status("running", 90, "Building dashboard visualizations")
    sample_limit = 350
    threshold_options = []
    for percentile in (95, 97, 99):
        candidate_threshold = float(np.percentile(val_mae, percentile))
        threshold_options.append({
            "percentile": percentile,
            "threshold": candidate_threshold,
            "flagged": int(np.sum(test_mae > candidate_threshold)),
        })

    results = {
        "status": "completed",
        "period_hours": round(count * 0.25, 2),
        "anomaly_ratio": round(float(np.mean(is_anomaly)) * 100, 2),
        "estimated_wastage_kwh": round(total_wastage, 4),
        "threshold": round(threshold, 6),
        "threshold_percentile": request.threshold_percentile,
        "detected_anomalies": int(np.sum(is_anomaly)),
        "interval_count": int(count),
        "statistical_anomalies": int(np.sum(statistical_anomalies)),
        "test_metrics": labeled_metrics,
        "timeline": [timestamp.isoformat() for timestamp in timeline_index],
        "actual_kw": [round(float(value), 5) for value in actual_kw],
        "reconstructed_kw": [round(float(value), 5) for value in reconstructed_kw],
        "anomaly_mask": [bool(value) for value in is_anomaly],
        "excess_kwh": [round(float(value), 5) for value in excess_kwh],
        "test_mae": [round(float(value), 6) for value in test_mae],
        "hourly_profile": [
            {"hour": int(hour), "kw": round(float(value), 5)}
            for hour, value in hourly.items()
        ],
        "weekly_profile": [
            {"day": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(day) % 7], "kw": round(float(value), 5)}
            for day, value in weekly.items()
        ],
        "training_history": {
            "loss": [round(float(value), 6) for value in history["loss"]],
            "val_loss": [round(float(value), 6) for value in history["val_loss"]],
        },
        "threshold_options": threshold_options,
        "distribution": [round(float(value), 5) for value in distribution],
        "sample_limit": sample_limit,
        "dataset": {
            "total_rows": int(len(resampled)),
            "train_rows": int(len(train_df)),
            "validation_rows": int(len(val_df)),
            "test_rows": int(len(test_df)),
        },
    }
    with state.lock:
        state.results = results
        state.status = "completed"
        state.progress = 100
        state.message = "Analysis complete"
    return results


@app.get("/api/health")
async def health():
    return {"status": "healthy", "service": "energy-wastage-api"}


@app.get("/api/status")
async def status():
    with state.lock:
        return {
            "status": state.status,
            "progress": state.progress,
            "message": state.message,
            "error": state.error,
        }


@app.post("/api/analyze")
async def analyze(request: AnalysisRequest):
    with state.lock:
        if state.status == "running":
            raise HTTPException(status_code=409, detail="An analysis is already running")
        state.status = "running"
        state.progress = 2
        state.error = None
        state.results = None
    asyncio.get_running_loop().run_in_executor(None, execute_analysis, request)
    return {"status": "started", "message": "LSTM analysis started"}


def execute_analysis(request: AnalysisRequest) -> None:
    try:
        run_analysis(request)
    except Exception as exc:
        set_error(str(exc))


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A dataset file is required")
    if not file.filename.lower().endswith((".txt", ".csv", ".zip")):
        raise HTTPException(status_code=400, detail="Upload a .txt, .csv, or .zip dataset")

    destination = DATA_DIR / "household_power_consumption.zip"
    if file.filename.lower().endswith(".zip"):
        destination.write_bytes(await file.read())
        try:
            safe_extract_zip(destination, DATA_DIR)
        except (zipfile.BadZipFile, ValueError) as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Invalid dataset ZIP: {exc}") from exc
        matches = list(DATA_DIR.glob("**/household_power_consumption.txt"))
        if not matches:
            raise HTTPException(status_code=400, detail="ZIP must contain household_power_consumption.txt")
        canonical_path = DATA_DIR / "household_power_consumption.txt"
        if matches[0].resolve() != canonical_path.resolve():
            canonical_path.write_bytes(matches[0].read_bytes())
    else:
        txt_destination = DATA_DIR / "household_power_consumption.txt"
        txt_destination.write_bytes(await file.read())
        try:
            header = pd.read_csv(txt_destination, sep=None, engine="python", nrows=0)
            required = {
                "Date",
                "Time",
                "Global_active_power",
                "Global_reactive_power",
                "Voltage",
                "Global_intensity",
                "Sub_metering_1",
                "Sub_metering_2",
                "Sub_metering_3",
            }
            missing = required.difference(header.columns.str.strip())
            if missing:
                raise ValueError(f"Dataset is missing required columns: {', '.join(sorted(missing))}")
        except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as exc:
            txt_destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Invalid dataset file: {exc}") from exc
    return {"status": "uploaded", "filename": file.filename}


@app.get("/api/results")
async def results():
    with state.lock:
        if state.results is None:
            return {"status": state.status, "message": state.message}
        return state.results


@app.get("/api/model")
async def model_file():
    path = MODEL_DIR / "lstm_autoencoder_wastage_model.keras"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Train an analysis to create the model")
    return FileResponse(path, filename=path.name)


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
