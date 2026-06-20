import os

try:
    import streamlit as st
    ORG_ID = st.secrets["ORG_ID"]
    TOKEN = st.secrets["TOKEN"]
    URL = st.secrets["URL"]
    APP_USERNAME = st.secrets["APP_USERNAME"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except:
    import dotenv
    dotenv.load_dotenv()
    ORG_ID = os.getenv('ORG_ID')
    TOKEN = os.getenv('TOKEN')
    URL = os.getenv('URL')
    APP_USERNAME = os.getenv('APP_USERNAME')
    APP_PASSWORD = os.getenv('APP_PASSWORD')
