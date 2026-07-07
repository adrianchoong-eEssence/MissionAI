from openai import OpenAI
import streamlit as st


client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)