from flask import Flask, render_template
from app.config import config
from app.api import api_bp


def create_app(config_name="default"):
    """Create and configure Flask application"""
    app = Flask(__name__, 
                template_folder="templates",
                static_folder="static")
    app.config.from_object(config[config_name])
    
    # Register API blueprint
    app.register_blueprint(api_bp)
    
    # Register routes
    @app.route("/")
    def index():
        return render_template("notes.html")
    
    @app.route("/notes")
    def notes_page():
        return render_template("notes.html")
    
    @app.route("/chat")
    def chat_page():
        return render_template("chat.html")
    
    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")
    
    return app
