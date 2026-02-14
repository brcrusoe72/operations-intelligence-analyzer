"""Repo-root entry point for Streamlit Cloud."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "traksys-oee-analyzer"))
# Re-export the real app so Streamlit Cloud picks it up
exec(open(os.path.join(os.path.dirname(__file__), "traksys-oee-analyzer", "streamlit_app.py")).read())
