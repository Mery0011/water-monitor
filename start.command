#!/bin/zsh
cd -- "${0:A:h}"
../.venv/bin/python -m streamlit run app.py --server.port 8503 --server.address 127.0.0.1 --browser.gatherUsageStats false
