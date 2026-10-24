# WindLens — Day-ahead wind forecast intelligence

WindLens is a full-stack pilot application for evaluating the accuracy of UK national wind generation forecasts before a day-ahead procurement decision. It was created for the Full Stack SWE challenge and is intentionally scoped to **January 2026 delivery intervals** and the two datasets named in the brief.

## What it does

- Loads actual half-hourly wind generation from Elexon BMRS `FUELHH`, filtered to `fuelType=WIND`.
- Loads wind generation forecasts from Elexon BMRS `WINDFOR`.
- Aggregates each pair of half-hourly FUELHH actual MW records into an hourly average to align with the hourly forecast target resolution; hours missing either half-hour actual remain unavailable.
- Chooses the latest `publishTime` available by a configurable day-before decision cutoff for each delivery hour. The default is **11:00 Europe/London**; this is an explicit assumption because the assignment does not give an exact clock time.
- Calculates MAE, RMSE, forecast bias, WAPE and record-coverage counts.
- Shows actual vs selected forecast, daily error, largest forecast misses, a detailed hourly table and CSV export.
- Provides a FastAPI health endpoint and API documentation.
- Uses Docker to package the React build and Python API in one deployable container.

**Scope note:** the brief restricts the analysis to wind actuals and forecasts. This app does not claim to calculate the exact additional power to procure, wholesale cost, demand deficit or monetary savings because those would require demand and/or market price data outside the assignment scope.

## Stack

- Frontend: React 18, Vite, custom responsive SVG charts
- Backend: Python 3.12, FastAPI, HTTPX
- Tests: pytest, FastAPI TestClient, mocked upstream data
- Packaging: Docker and Docker Compose
- Data source: Elexon Insights / BMRS API

## Project layout

```text
windlens_assignment_project/
├── backend/
│   ├── app/
│   │   ├── analytics.py       # Vintage selection, interval matching, accuracy metrics
│   │   ├── elexon.py          # Elexon HTTP client and short-lived cache
│   │   └── main.py            # FastAPI routes and production static serving
│   ├── tests/
│   │   ├── test_analytics.py  # Metric, cutoff and matching tests
│   │   └── test_api.py        # Health, validation, JSON and CSV route tests
│   ├── requirements.txt       # Runtime dependencies
│   └── requirements-dev.txt   # Runtime plus pytest
├── frontend/
│   ├── src/
│   │   ├── components/        # SVG line chart and daily error bars
│   │   ├── services/api.js    # Backend API and CSV URL client
│   │   ├── App.jsx            # Dashboard, filters, explorer and methodology
│   │   ├── main.jsx           # React entry point
│   │   └── styles.css         # Responsive styles
│   ├── index.html
│   ├── package.json
│   └── vite.config.js         # Local API proxy
├── Dockerfile                 # Multi-stage React build + Python runtime
├── compose.yaml               # One-command local container deployment
├── .env.example               # Documented environment variables (no secrets)
├── .dockerignore
└── README.md
```

## Quick start with Docker (recommended)

Requirements: Docker Desktop or Docker Engine with the Compose plugin, plus outbound internet access from the container to `data.elexon.co.uk`.

From the project root:

```bash
docker compose up --build
```

Open:

- App:https://windlens-january-2026.vercel.app
- Health check: <http://localhost:8000/api/health>
- Interactive API docs: <http://localhost:8000/docs>

Stop with `Ctrl+C`, or run `docker compose down` in a second terminal.

The first image build requires internet access to install npm and Python packages. The application does not include fake production data: if Elexon is unavailable, it displays a visible error instead of fabricating results.

## Local development without Docker

### 1. Backend

Python 3.11+ is supported (the Docker runtime uses Python 3.12).

Windows PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

macOS/Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (second terminal)

```bash
cd frontend
npm install
npm run dev
```

Vite runs at <http://localhost:5173> and proxies `/api` calls to `http://127.0.0.1:8000` by default. Set `VITE_API_PROXY_TARGET` if the backend is running elsewhere.

## API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Basic service status; does not call Elexon |
| `GET /api/analysis` | Returns metrics, coverage, daily summaries, largest errors and interval records |
| `GET /api/records.csv` | Downloads the selected interval records as CSV |
| `GET /docs` | Interactive FastAPI API documentation |

Example:

```text
/api/analysis?start_date=2026-01-01&end_date=2026-01-31&cutoff_hour=11
```

Date bounds are inclusive UK delivery dates and are intentionally restricted to 1–31 January 2026. `cutoff_hour` is an integer from 0 to 23 and is interpreted as Europe/London time on the preceding day.

## Analytical method

1. Request `FUELHH` using `settlementDateFrom` / `settlementDateTo` and `fuelType=WIND`, then filter again client-side to `fuelType=WIND` for defence in depth.
2. Request `WINDFOR` using `publishDateTimeFrom` / `publishDateTimeTo`, covering the day before the first requested delivery date through the day before the last requested date; retain `publishTime` alongside target `startTime` and `generation`.
3. For each hourly target, calculate the configured previous-day cutoff in `Europe/London`, then select the forecast with the latest `publishTime` that is no later than that cutoff.
4. Average the two half-hour FUELHH MW values within each clock hour. If either half-hour value is missing, mark that hourly actual unavailable. Match hourly actuals and selected hourly forecasts on the hour start timestamp. Incomplete actual pairs and missing forecasts contribute to coverage figures but are excluded from accuracy metrics.
5. Compute:
   - `MAE = mean(abs(forecast - actual))`
   - `RMSE = sqrt(mean((forecast - actual)^2))`
   - `Bias = mean(forecast - actual)` (positive means overforecasting)
   - `WAPE = sum(abs(forecast - actual)) / abs(sum(actual)) * 100`; omitted if total actual generation is zero.

The API response includes the cutoff, methodology, and raw record counts returned by each source so an empty upstream response can be distinguished from a cutoff/matching issue. The selected cutoff should be confirmed with the hiring team/client before interpreting the output as a real trading recommendation.

## Run tests

From the project root:

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The tests use synthetic fixtures strictly in unit tests and mock Elexon; they do **not** represent measured January 2026 generation or forecast results. No live data is embedded in the production app.

## Deployment to Heroku using Docker

The assignment asks for Docker and deployment to Vercel or Heroku. This repo packages the API and static frontend together in a single Docker image, so **Heroku Container Registry** is the most direct path.

Requirements: a Heroku account with container deployment/billing enabled, Heroku CLI, Git, Docker Desktop/Engine, and an available globally unique app name. The hosting account is owned by you; no tokens or credentials are stored in this repo.

1. Install and authenticate the Heroku CLI, then log in:

   ```bash
   heroku login
   heroku container:login
   ```

2. Create a new app with an available name (use your anonymous repository name or another neutral identifier):

   ```bash
   heroku create YOUR-UNIQUE-APP-NAME
   ```

3. Build and push this project's Docker image:

   ```bash
   heroku container:push web --app YOUR-UNIQUE-APP-NAME
   ```

4. Release it and open the app:

   ```bash
   heroku container:release web --app YOUR-UNIQUE-APP-NAME
   heroku open --app YOUR-UNIQUE-APP-NAME
   ```

5. Verify these routes from an incognito browser:

   ```text
   https://YOUR-UNIQUE-APP-NAME.herokuapp.com/
   https://YOUR-UNIQUE-APP-NAME.herokuapp.com/api/health
   https://YOUR-UNIQUE-APP-NAME.herokuapp.com/docs
   ```

Heroku availability, container support and pricing can change; check your account's current plan before relying on this route. Do not add a secret API key: the configured Elexon public API endpoints are used without a personal credential in this app. If your deployment platform requires any secret, set it only in the provider dashboard, never in Git.

## AI-tool disclosure for the assignment

The challenge explicitly asks candidates to disclose AI tools in the README when used. Before submission, replace or supplement this sentence with the exact tools you used and describe which parts you reviewed and tested:

> AI-tool disclosure: OpenAI ChatGPT was used as an implementation assistant for project scaffolding, code drafting, documentation and test planning. The submitted code and analytical assumptions were reviewed and tested by the candidate; AI-generated output was not treated as evidence of live Elexon results.

Keep this disclosure accurate to your actual workflow.

## Pre-submission checklist

- [ ] Run tests using the commands above.
- [ ] Build the Docker image and open the app locally.
- [ ] Confirm the Elexon API has returned real January 2026 rows; don't mistake a healthy `/api/health` response for a successful data request.
- [ ] Check the cutoff assumption and explain it in the demo.
- [ ] Ensure the public GitHub repository name is anonymous as requested.
- [ ] Update the AI-tool disclosure to reflect your usage.
- [ ] Deploy and test the live app, API health route, and CSV download in incognito mode.
- [ ] Record the mandatory unlisted YouTube video: customer overview (≤5 min) + technical walkthrough (≤5 min), total ≤10 min.
- [ ] Complete the challenge submission form and check every URL in incognito mode.

## References

- Elexon FUELHH stream: <https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream>
- Elexon WINDFOR stream: <https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream>
- Elexon API endpoint catalogue: <https://bmrs.elexon.co.uk/api-documentation/endpoint>
