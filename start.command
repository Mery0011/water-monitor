#!/bin/zsh
set -u

project_dir="${0:A:h}"
cd -- "$project_dir" || exit 1
python_bin="$project_dir/.venv/bin/python"

wait_before_exit() {
    if [[ -t 0 ]]; then
        read -r "?Press Enter to close..."
    fi
    exit 1
}

if [[ ! -x "$python_bin" ]]; then
    print -r -- "Water Monitor: the project's Python environment was not found."
    print -r -- "Open a terminal and run:"
    print -r -- "  cd ${(q)project_dir}"
    print -r -- "  python3 -m venv .venv"
    print -r -- "  .venv/bin/python -m pip install -r requirements.txt"
    print -r -- "Then open start.command again."
    wait_before_exit
fi

if ! "$python_bin" -c 'import streamlit, sklearn, pandas, numpy, joblib, altair, psycopg' >/dev/null 2>&1; then
    print -r -- "Water Monitor: required Python packages could not be loaded."
    print -r -- "Open a terminal and run:"
    print -r -- "  cd ${(q)project_dir}"
    print -r -- "  .venv/bin/python -m pip install -r requirements.txt"
    print -r -- "Then open start.command again."
    wait_before_exit
fi

exec "$python_bin" -m streamlit run "$project_dir/app.py" \
    --server.port 8503 --server.address 127.0.0.1 --browser.gatherUsageStats false
