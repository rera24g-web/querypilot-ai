import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["APP_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/app.db"
