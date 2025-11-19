import os
import logging
from flask import Flask, redirect, url_for, request, flash
from flask_login import LoginManager, current_user
from .models import db, Setting, User
from .controllers.main_controller import main_bp

login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    #integrate flask logging mechanism with WSGI logging (eg. gunicorn)
    if __name__ != 'main':
        gunicorn_logger = logging.getLogger('gunicorn.error')
        app.logger.handlers = gunicorn_logger.handlers
        app.logger.setLevel(gunicorn_logger.level)

    if test_config is None:
        app.config.from_mapping(
            SECRET_KEY=os.getenv('SECRET_KEY', 'dev'),
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(app.instance_path, 'database.db')}",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
    else:
        app.config.from_mapping(test_config)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    db.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(main_bp)

    @app.before_request
    def before_request_handler():
        if request.endpoint and request.endpoint in ['static', 'main.get_version']:
            return

        with app.app_context():
            user_exists = User.query.first()

            if not user_exists:
                if request.endpoint != 'main.setup':
                    return redirect(url_for('main.setup'))
                return

            if current_user.is_authenticated:
                token_exists = Setting.query.filter_by(key='API_GITHUB_TOKEN').first()

                if not token_exists:
                    allowed_endpoints = ['main.settings', 'main.logout']
                    if request.endpoint not in allowed_endpoints:
                        flash('Please configure the GitHub API Token in the settings.', 'warning')
                        return redirect(url_for('main.settings'))

    return app