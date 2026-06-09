"""
Test bootstrap — must run before `main` is imported.

- Pins every sensitive env var to a dummy value so importing the app can
  never touch real providers, and so a developer's .env can't leak into
  tests (load_dotenv never overrides variables that are already set).
- chdirs into a throwaway temp dir so the app's relative sqlite path
  (./lexio.db) creates a scratch database instead of the real one.
"""
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ADMIN_KEY"] = "test-admin-key"
os.environ["OPENAI_API_KEY"] = "test-openai-key"
os.environ["GOOGLE_API_KEY"] = "test-google-key"
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
os.environ["STRIPE_SECRET_KEY"] = ""
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
for var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"):
    os.environ[var] = ""
os.environ["SMTP_PORT"] = "587"  # app does int() on it; empty would crash

_scratch = Path(tempfile.mkdtemp(prefix="lexio-tests-"))
# The app mounts StaticFiles(directory="static") relative to cwd.
os.symlink(REPO_ROOT / "static", _scratch / "static")
os.chdir(_scratch)

sys.path.insert(0, str(REPO_ROOT))
