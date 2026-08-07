"""Flask application factory."""

from pathlib import Path

from flask import Flask

from ..core import ExportPipeline
from .routes import bp
from .storage import MemoryResultStore

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def create_app(pipeline=None, results=None):
    app = Flask(__name__, static_folder=str(STATIC_DIR),
                static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024
    app.extensions["pipeline"] = pipeline or ExportPipeline()
    app.extensions["results"] = results or MemoryResultStore()
    app.register_blueprint(bp)
    return app
