# Deploy Water Monitor with Streamlit Community Cloud and Supabase

This deployment remains a synthetic portfolio prototype. Each browser session has
its own simulation, while incident history and contacts are shared in the configured
database. It does not receive real meter data or run monitoring without a browser.
Use sample contacts in a public demo: the current UI lets viewers edit contacts and
inspection results. A private operational deployment needs access controls first.

## 1. Create the database

Create a Supabase **Free** project. Keep the database password in a password manager.
In **Connect**, copy the **Session pooler** PostgreSQL connection string (port 5432;
IPv4 compatible). Replace the password placeholder and percent-encode special
characters. Include `sslmode=require`. Do not paste the password into chat or GitHub.

The application creates its tables in a separate `water_monitor` schema. Leave
this schema out of Supabase's exposed Data API schemas. No browser-side database
key or Data API access is needed. All queries run on the Streamlit server.

## 2. Deploy the app

After reviewing, committing, and pushing the deployment changes, create an app in
Streamlit Community Cloud with:

- Repository: `Mery0011/water-monitor`
- Branch: `develop` (or a reviewed release merged into the default branch)
- Entry point: `app.py`
- Python: choose a version supported by all pinned packages (local validation uses 3.14)

Under **Advanced settings > Secrets**, copy the shape from
`.streamlit/secrets.toml.example` and replace the placeholder URL privately.
Do not create a public `secrets.toml` file. `requirements.txt` installs the model's
pinned scikit-learn version and the PostgreSQL driver. Keep the tracked model and
metrics artifacts in the deployment.

## 3. Check persistence

1. Start a demo incident and save an inspection note.
2. Open a fresh browser session and confirm the incident remains in history.
3. Reboot the app from the hosting dashboard and confirm the same history and contacts.
4. Resolve a saved incident and confirm the change appears after refresh in the other window.
5. In Supabase, check `water_monitor.incidents` and `water_monitor.contacts`.

Do not unset the database URL if Supabase is unavailable. A configured cloud
connection failure must show an error, rather than silently write to temporary
SQLite storage. With no cloud URL, local development continues using SQLite.
`WATER_MONITOR_DB` explicitly selects local SQLite and takes precedence for tests.
Do not set it on Community Cloud.

## Backups and free-plan limitations

An external database survives app redeploys, but it is not an unlimited retention
or backup guarantee. Export the database periodically with Supabase's documented
backup tools and keep a separate private copy. Free projects can pause after low
activity; check and resume the project before an interview. Do not upload private
local contacts or old incident history automatically to an open demo.

## PostgreSQL integration checks

Use a disposable database whose name ends in `_test`. Set
`WATER_MONITOR_TEST_DATABASE_URL` and run `.venv/bin/python -B check_postgres.py`.
The check clears tables in that database's `water_monitor` schema. Never use a
production database URL for this check. The normal `checks.py` suite always uses
its temporary local SQLite database.

## References

- [Streamlit deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)
- [Streamlit secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Supabase database connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase free project pausing](https://supabase.com/docs/guides/platform/free-project-pausing)
- [Supabase backups](https://supabase.com/docs/guides/platform/backups)
