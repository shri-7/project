# WattWatch: Hidden Electrical Energy Wastage Detection

A complete LSTM Autoencoder project for detecting hidden household electricity wastage using 15-minute UCI Household Power Consumption records.

## Google Colab

Open `colab_energy_wastage.ipynb` in Google Colab. The notebook is the reference implementation and includes:

- Dataset download with fallback URLs
- First 250,000-row stability subset
- Missing-value interpolation
- 15-minute resampling
- Chronological 70/15/15 split
- Training-only MinMax scaling
- 96-step (24-hour) sequences
- LSTM Autoencoder training
- 99th-percentile reconstruction-error threshold
- kWh wastage quantification
- EDA and anomaly visualizations
- Rolling-mean baseline comparison
- Threshold sensitivity experiments

The notebook saves `lstm_autoencoder_wastage_model.keras` for local dashboard use. To generate the optional known-label test data, run `python energy-wastage/scripts/create_sample_data.py` from the repository root.

## Web application

The backend serves the robust responsive frontend at `http://localhost:8000`.

```bash
cd energy-wastage/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

For checks without starting a server, install the development requirements and run `python -m pytest -q ../tests` from this backend directory:

```bash
pip install -r requirements-dev.txt
python -m pytest -q ../tests
```

The end-to-end test trains the LSTM on the included synthetic file and measures precision, recall, and F1 on the held-out labeled test windows.

## Dataset

The application tries the official UCI archive and a GitHub mirror. You can also upload `household_power_consumption.txt`, a CSV, or a ZIP containing that file from the dashboard. For a known-label end-to-end check, upload [sample_household_power_consumption.csv](./data/sample_household_power_consumption.csv). Its 15-minute synthetic readings contain three labeled high-consumption events in the test split; F1, precision, and recall are then computed against those known labels. These metrics are sequence-window classification metrics, not unsupervised metrics on unlabeled UCI data.

## API

- `GET /api/health` – service health
- `POST /api/upload` – upload a local dataset
- `POST /api/analyze` – start background LSTM analysis
- `GET /api/status` – training progress
- `GET /api/results` – dashboard data
- `GET /api/model` – download the trained Keras model

## Reliability and limitations

- Chronological splitting prevents future observations from entering training.
- Scaling is fit only on training data.
- Early stopping restores the best validation weights.
- The system labels statistically unusual positive residuals; it does not prove that an appliance or behavior caused wastage.
- Ground-truth anomaly labels are unavailable, so the unsupervised result is a ranked estimate rather than a precision/recall score.
- The included synthetic sample has ground-truth labels solely to test the pipeline; do not treat its metrics as real-household performance.
