import os
import tempfile

# Keep test runs from writing into the real data/ folder. Must happen before
# bot_v.config is imported (it reads the environment once).
os.environ.setdefault("BOTV_DATA_DIR", tempfile.mkdtemp(prefix="botv-test-"))
