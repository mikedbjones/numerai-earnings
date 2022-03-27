from flask import Flask

def init_app():
    """Construct core Flask application with embedded Dash app."""
    app = Flask(__name__, instance_relative_config=False)

    with app.app_context():

        # # blueprint for non-auth parts of app
        # from .main import main as main_blueprint
        # app.register_blueprint(main_blueprint)

        # Import dashboard app
        from .dashboard.dashboard import init_dashboard
        app = init_dashboard(app)

        return app
