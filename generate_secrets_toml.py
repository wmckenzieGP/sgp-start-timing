"""
Run this script once locally to generate the TOML block for Streamlit Cloud secrets.
Output is printed to the terminal — copy it, then paste into:
  Streamlit Cloud → your app → Settings → Secrets

This file is gitignored (*.py in root is fine, but the OUTPUT must never be committed).
"""
import json, sys

creds_file = 'blackfoilsdata-0475bd5996f2.json'
try:
    with open(creds_file) as f:
        d = json.load(f)
except FileNotFoundError:
    sys.exit(f"ERROR: {creds_file} not found. Run this from the project root.")

lines = ['[gcp_service_account]']
for k, v in d.items():
    # Preserve literal \n in the private key inside the TOML string
    escaped = str(v).replace('\n', '\\n')
    lines.append(f'{k} = "{escaped}"')

print('\n'.join(lines))
print('\n--- Copy everything above into Streamlit Cloud Secrets ---')
