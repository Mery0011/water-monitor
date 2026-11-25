# Water Monitor — AI-Assisted Water Usage Monitoring

Water Monitor is a portfolio prototype that helps building security staff identify unusual apartment water usage, investigate alerts, and retain inspection history. It combines an Isolation Forest model with a Streamlit dashboard for 15 virtual apartments.

**[Open the live demo](https://water-monitor.streamlit.app/)** · [Portfolio notes](PORTFOLIO.md) · [Deployment guide](DEPLOYMENT.md)

**All water readings are synthetic. No physical meter or valve is connected.** “Live time” follows the real clock; it does not mean the app receives real sensor readings. The prototype flags situations for inspection rather than confirming leaks.

![Water Monitor dashboard](docs/images/english-panel.png)

## Features

- Fifteen apartment status cards with water-flow charts.
- Live-time simulation in Asia/Seoul (UTC+9), with one reading per real minute.
- Accelerated demo with manual 15-minute steps and automatic playback.
- Normal usage, continuous leak, 15-minute shower, and disconnected-sensor scenarios.
- Alert explanations showing why an incident was flagged and what staff should check.
- Acknowledge, investigate, and complete inspections with outcomes and staff notes.
- Paginated alerts: five per page, oldest first, with inspection drafts retained across pages.
- A single incident history covering all sessions, including date/time and CSV report export.
- Editable apartment owner contacts with phone-handler and email-draft links; nothing is sent automatically.
- PostgreSQL persistence on Supabase for the deployed app and SQLite for local development.
- A dedicated model-results tab comparing the detector with 20- and 60-minute rules.
- English by default, with Korean and Uzbek available. Language changes preserve session state and staff notes.

## Live deployment

The public demo runs on **Streamlit Community Cloud**, with incident history and contacts stored separately in **Supabase PostgreSQL**. The deployment uses the `develop` branch.

```text
Browser → Streamlit dashboard + trained model ↔ Supabase PostgreSQL
```

Each browser session has its own simulated readings and scenarios. Saved history and contacts are shared through the database. The current app is not a centralized feed from real meters, and monitoring does not run independently of browser sessions.

**Use sample information in the public demo.** There is no staff login or role-based access control; viewers can edit contacts and inspection results. Sample contacts have calling and email actions disabled.

Free hosting can sleep or pause. Check the app and Supabase project before a presentation. External database storage survives app redeploys, but separate backups are still needed.

## Run locally

Tested with Python 3.14. These commands use a macOS/Linux terminal:

```sh
git clone https://github.com/Mery0011/water-monitor.git
cd water-monitor
git switch develop
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.port 8503 --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Open [localhost:8503](http://127.0.0.1:8503). Keep the terminal open; press **Ctrl+C** to stop. If the port is occupied, stop the existing instance or choose another port.

On macOS, you can also double-click `start.command` after installing dependencies. It uses the project's own `.venv` and displays setup instructions if it is missing. Recreate `.venv` after moving the project to a different path.

The trained model is included in `artifacts/`. No paid AI API, AI API key, or GPU is required. Only load joblib model files from trusted sources.

## Two-minute demonstration

1. Open the app and select **Accelerated demo**. Live-time mode would require real elapsed minutes.
2. Select **Apartment 03** and click **Start leak**.
3. Click **+15 minutes** twice. This adds a simulated continuous leak of 0.7 L/min; the example should produce an alert after sufficient continuous readings.
4. Read **Why this alert?** and click **Acknowledge**.
5. Open **Complete inspection**, enter a note, and choose an outcome:
   - **Leak fixed → Resolve:** completes the inspection and stops the simulated leak.
   - **Normal usage → Resolve:** completes the inspection without stopping water flow.
   - **Cause unknown → Save inspection:** saves the note and keeps the incident acknowledged and open for investigation.
6. Click **Disconnect sensor** to create an immediate connection alert, including while paused. Resolve it as **Connection restored** to reconnect the simulated sensor. **Device inspection required** records the outcome but leaves it offline.
7. Try **Shower — 15 minutes**: 7 L/min for 15 virtual minutes, ending automatically. A short shower starting from no continuous flow does not meet the detector's 20-reading persistence condition.
8. Open **Incident history** to inspect saved outcomes or download the report.

Automatic demo playback advances five virtual minutes every two seconds. The accelerated day ends at 23:59; live-time simulation continues across midnight. Resetting or switching time mode creates a new simulation without deleting saved incident history.

A flat line at zero is a valid reading, not a broken chart. Scenario changes normally take effect at the next reading; a manually disconnected sensor is marked offline immediately. On a live-time resume or scenario change, elapsed readings are processed under the previous scenario before the change is applied.

## Inspection workflow and permanent history

Inspection status and signal activity are separate:

| Outcome | Inspection status | Effect on the simulated signal |
|---|---|---|
| Leak fixed | Resolved | Stops the simulated leak |
| Normal usage | Resolved | Flow continues; no duplicate incident for the same uninterrupted signal |
| Cause unknown | Acknowledged / in progress | Flow and the pending inspection remain |
| Connection restored | Resolved | Reconnects the simulated sensor immediately |
| Device inspection required | Resolved | Sensor remains offline |

No outcome controls a physical valve. When a continuous signal ends, a later signal can create a new incident.

**Incident history** includes current and previous sessions. Archived pending incidents can still be acknowledged or completed, but these actions do not control the current simulation. New incidents retain their start date and time. Legacy records without a stored date display **Date unavailable** instead of an invented date. Accelerated-demo timestamps use the same virtual date as the chart.

Incidents, inspection outcomes, notes, contacts, and audit entries are stored in the configured database. Full minute-by-minute telemetry and playback state are not restored after a restart. The UI currently shows incident records rather than a full audit-event browser.

Repeated saves do not duplicate incidents. Workflow writes use transactions and compare the last saved state to prevent stale windows from overwriting newer inspection results. Conflicting edits preserve the newer saved result and show a notice.

## Contacting an owner

Select an apartment and open **Contact owner**. Edit the name, phone, and email, then click **Save contact**. To enable contact actions, clear **Sample contact (disable calling and email)**. Unused fields can be left blank.

**Call owner** opens the device's phone handler. **Draft email** opens the default email application with a localized message. The app does not make calls, send email, or confirm that an owner has been reached. Historical incidents use the apartment's current saved contact.

## Model and evaluation

The project trains an existing **Isolation Forest** algorithm using scikit-learn; it does not introduce a new machine-learning algorithm.

- **Training:** 60 independent synthetic days without leaks; 40,000 sampled rows; 160 trees, `max_samples=512`, and `random_state=42`.
- **Features:** current flow, trailing 15/60-minute means, trailing 15-minute variability, continuous-flow duration, and sine/cosine time-of-day features. No future readings are used.
- **Validation:** 24 separate synthetic days; the threshold is selected by minute-level F1 and is no lower than the 95th percentile of normal training scores.
- **Detector:** anomaly score above the threshold **and** at least 20 consecutive active readings. The score is not a leak probability.
- **Test:** 24 additional synthetic household-days: 12 with leaks and 12 without. Training, validation, testing, and the dashboard use distinct seeds.

### Synthetic test results

| Method | Precision | Recall | F1 | Leak days detected | Normal days with alerts | Median delay |
|---|---:|---:|---:|---:|---:|---:|
| AI + 20-minute condition | 91.1% | 88.1% | 89.6% | 12/12 | 5/12 | 19 min |
| 20-minute rule | 91.1% | 88.2% | 89.7% | 12/12 | 5/12 | 19 min |
| 60-minute rule | 98.5% | 63.3% | 77.0% | 12/12 | 0/12 | 59 min |

Precision, recall, and F1 are measured **per minute**. A detected leak day means at least one leak minute was flagged, not that every leak minute was detected. Delays cover detected incidents only; twenty consecutive readings span nineteen minutes from first to last.

**The AI did not improve on the simple 20-minute rule in this synthetic test.** The 60-minute rule reduced false alerts but delayed detection. The fixed results do not change when someone uses the demo. Raw minute-level predictions are evaluated separately from the dashboard's incident-retention policy.

Real sensor data and labelled incidents are needed to establish practical performance. Long legitimate usage can trigger alerts; small or intermittent leaks may be missed.

## Database configuration and deployment

| Configuration | Storage |
|---|---|
| No cloud URL configured | Local `data/water-monitor.sqlite3` |
| `WATER_MONITOR_DATABASE_URL` in environment or Streamlit Secrets | External PostgreSQL |
| Explicit `WATER_MONITOR_DB` path | Local SQLite, overriding cloud configuration for local use and tests |

A configured cloud database failure is reported; it does not silently fall back to temporary local storage. PostgreSQL tables are created in the separate `water_monitor` schema, which should remain outside Supabase's exposed Data API schemas.

Keep credentials in Streamlit Secrets, never GitHub. Local databases, journal files, and SQLite backups are ignored by Git. Retain the local `data/` folder when moving the project, and take consistent backups before making database changes.

See [DEPLOYMENT.md](DEPLOYMENT.md) for Supabase connection settings, Streamlit setup, persistence checks, and backup considerations.

## Retraining and checks

```sh
# Optional: regenerate the model and evaluation artifacts.
.venv/bin/python train.py

# Local regression suite; uses temporary SQLite databases.
.venv/bin/python -B checks.py

# macOS launcher checks; does not launch a real server.
.venv/bin/python -B check_launcher.py

# Configuration checks plus optional PostgreSQL integration checks.
.venv/bin/python -B check_postgres.py
```

PostgreSQL integration checks require `WATER_MONITOR_TEST_DATABASE_URL` pointing to a **disposable database whose name ends in `_test`**. They clear that test database's application tables. Without this setting, PostgreSQL integration cases are skipped; configuration checks still run. Never use the deployed database for these tests.

Checks cover causal features, missing readings, shower/leak scenarios, incident lifecycle, inspection outcomes, timestamps across midnight, saved history across sessions, contact validation, multilingual UI, paginated alerts, stale-window conflicts, audit migration, transactional rollback, and concurrent PostgreSQL audit writes.

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Dashboard, alert explanations, inspection UI, history, and model results |
| `engine.py` | Synthetic readings, causal features, detection, and simulation state |
| `database.py` | SQLite/PostgreSQL connections, schema initialization, and write locking |
| `storage.py` | Incident persistence and archived inspection updates |
| `contacts.py` | Contact validation, persistence, and phone/email links |
| `train.py` | Model training, validation, and test evaluation |
| `i18n.py` | English, Korean, and Uzbek translations |
| `checks.py` | Application and SQLite regression checks |
| `check_postgres.py` | Cloud configuration and PostgreSQL integration checks |
| `check_launcher.py` | macOS launcher checks |
| `start.command` | macOS launcher using the project's `.venv` |
| `artifacts/` | Trained model, evaluation metrics, and a sample synthetic day |
| `.streamlit/secrets.toml.example` | Credential-free cloud configuration template |
| `DEPLOYMENT.md` | Hosting and database setup guide |
| `PORTFOLIO.md` | Portfolio description and presentation notes |

## Branches and future work

- **master:** main branch; reviewed changes can be merged here.
- **develop:** development branch, currently used by the live demo. Pushing here can update the deployed app.

Next steps for a real pilot include agreeing on a meter data format, connecting one sensor, collecting labelled measurements, re-evaluating against simple rules, and adding staff authentication, backups, schema migrations, network buffering, and operational monitoring. Large datasets and production workloads have not been validated. This prototype is not ready for unattended building security use.
