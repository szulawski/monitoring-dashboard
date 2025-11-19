# tests/conftest.py

import pytest
from app import create_app
from app.models import db, User, Setting
from app.utils import encrypt_data
from sqlalchemy import text

@pytest.fixture(scope='module')
def test_app():
    """Creates a test instance of the app for the duration of all tests."""
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'SERVER_NAME': 'localhost.local'
    })
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture()
def client(test_app):
    """Provides a test client for the app."""
    with test_app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def db_session(test_app):
    """
    Ensures a clean database session for each test.
    Using autouse=True makes this fixture automatically used by every test.
    """
    with test_app.app_context():
        yield db.session
        
        # Teardown: Clean up the database
        db.session.remove()
        
        # THIS IS THE FIX: Use the correct SQLAlchemy 2.0+ pattern for raw SQL execution
        with db.engine.connect() as connection:
            transaction = connection.begin()
            for table in reversed(db.metadata.sorted_tables):
                connection.execute(table.delete())
            transaction.commit()


@pytest.fixture()
def auth_client(client, db_session):
    """
    A fixture that creates a test user and logs them in.
    Returns an authenticated test client.
    """
    user = User(username='testuser')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    client.post('/login', data={'username': 'testuser', 'password': 'password'}, follow_redirects=True)
    yield client
    client.get('/logout', follow_redirects=True)


@pytest.fixture()
def configured_client(auth_client, db_session):
    """
    A fixture that provides a fully authenticated and configured client.
    (User is logged in, and GitHub token is set).
    """
    setting = Setting(key='API_GITHUB_TOKEN', value=encrypt_data('fake-github-token'))
    db_session.add(setting)
    db_session.commit()
    yield auth_client