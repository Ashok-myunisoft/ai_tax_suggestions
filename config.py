import os
from dotenv import load_dotenv

load_dotenv()   

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DATA_PATH      = os.getenv("DATA_PATH", "data/employees.json")
FAISS_DIM      = 1536
OPENAI_EMBED   = "text-embedding-3-small"
OPENAI_CHAT    = "gpt-4o-mini"

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")