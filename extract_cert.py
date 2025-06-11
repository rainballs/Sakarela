# extract_cert.py
import json

# 1) Load the JSON
cfg = json.load(open("mypos_config.json", "r"))

# 2) Get the raw certificate string (with literal "\r\n")
raw = cfg["pc"]

# 3) Replace the JSON escapes with real newlines
pem = raw.replace("\\r\\n", "\n")

# 4) Write it out
with open("mypos_public.pem", "w") as f:
    f.write(pem)

print("Wrote mypos_public.pem")
