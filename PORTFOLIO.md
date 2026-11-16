# Water Monitor — Apartment Water Monitoring Prototype

## Problem and users

An undetected apartment water leak can waste water and damage neighboring units. Building security staff need a way to identify apartments that require inspection and record the outcome.

## Solution

A local web dashboard monitors minute-by-minute synthetic water readings from 15 virtual apartments. An Isolation Forest model combined with a continuous-flow condition flags unusual usage for staff review.

Staff can acknowledge an alert, record an inspection outcome and notes, resolve the incident, and export its history as CSV. Sensor disconnection is tracked separately from water incidents. Resolving an active water incident also stops the simulated leak; it does not control a real valve.

Staff can view owner contacts from apartment and incident panels. Fictional sample contacts have disabled actions; configured contacts can open a phone handler or a prefilled email draft. Calls and messages are never sent automatically.

The interface defaults to English and supports Korean and Uzbek. Live-time mode follows Asia/Seoul time (UTC+9), while accelerated mode supports a short interview demonstration. All readings in both modes are synthetic.

## Technology and implementation

Python, scikit-learn, pandas, NumPy, Altair, and Streamlit. The Isolation Forest model was trained on normal synthetic household-days, with separate validation and test days. Features use current and historical readings without looking ahead. The model runs locally without a paid AI API.

The project includes synthetic telemetry generation, model training and evaluation, a multilingual dashboard, incident state management, CSV reports, a persistent SQLite incident archive, an editable local owner directory with phone/email links, and automated regression checks.

## Results and lessons

On 24 synthetic test days, the hybrid detector achieved **91.1% precision** and **88.1% recall**, measured per minute. It flagged at least one leak minute on all 12 leak days, but also raised alerts on 5 of the 12 normal days.

The AI did **not** outperform a simple 20-minute continuous-flow rule on this dataset. A 60-minute rule reduced false alerts but delayed detection. This comparison demonstrates why a model should be evaluated against a simple baseline and why false alerts matter alongside detection rates.

These results describe this synthetic test set only; they do not demonstrate reliable performance in an occupied building. The next step is to collect real sensor readings and labeled incidents, then assess whether the model adds practical value.

## Scope and limitations

This is a portfolio prototype with no physical meter connection or real-world validation. It does not provide SMS delivery, automatic water shutoff, a production audit service, or staff authentication and access roles. Incident history, outcomes, and staff notes are saved in a local SQLite database and survive restarts; simulation telemetry and playback position remain in session memory. Archived inspections can be completed without changing the current simulation. The model flags situations for inspection rather than confirming leaks.

## Portfolio presentation

Use a screenshot of the actual dashboard as the project cover, followed by a short explanation of the problem, solution, evaluation, and limitations. A 30–60 second demonstration can show:

1. Start a simulated leak and advance demo time.
2. Show the alert and acknowledge it.
3. Record an inspection outcome and resolve the incident.
4. Show the restored apartment status and retained incident history.

Link to the GitHub repository containing the README, source code, checks, and evaluation metrics. Do not upload the virtual environment. A localhost address is a local demo address, not a publicly hosted application.
