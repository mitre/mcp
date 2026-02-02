import os
import litellm

# -------------------------------
# REQUIRED CONFIG
# -------------------------------
API_KEY = "sk-REPLACE_ME"
API_BASE = "https://models.k8s.aip.mitre.org"

MODEL = "huggingface/nvidia/llama-embed-nemotron-8b"

# -------------------------------
# ENV SETUP (matches your app)
# -------------------------------
os.environ["OPENAI_API_KEY"] = API_KEY
os.environ["OPENAI_API_BASE"] = API_BASE

# -------------------------------
# TEST CALL
# -------------------------------
print("Testing embedding model:", MODEL)

response = litellm.embedding(
    model=MODEL,
    input="BlackCat ransomware uses data exfiltration and credential access.",
)

print("SUCCESS")
print("Embedding vector length:", len(response["data"][0]["embedding"]))
