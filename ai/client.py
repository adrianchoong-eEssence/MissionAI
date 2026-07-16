import os

import streamlit as st
from openai import OpenAI


@st.cache_resource
def get_openai_client():
    try:
        api_key = str(st.secrets["OPENAI_API_KEY"]).strip()
    except Exception:
        api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    return OpenAI(api_key=api_key)
