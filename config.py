import os

try:
    import streamlit as st
    # 1. When running on the internet, this looks in your Streamlit Cloud vault
    ORG_ID = st.secrets["ORG_ID"]
    TOKEN = st.secrets["TOKEN"]
    URL = st.secrets["URL"]
except:
    # 2. When running on your laptop, the cloud vault isn't there, so it falls back to your local setup
    import dotenv
    dotenv.load_dotenv()
    
    ORG_ID = os.getenv('ORG_ID')
    TOKEN = os.getenv('TOKEN')
    URL = os.getenv('URL')