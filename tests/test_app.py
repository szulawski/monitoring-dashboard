# tests/test_app.py

# THIS IS THE FIX: Added 'db' to the import list
from app.models import db, Setting, AzureDevOpsConfig, MonitoredADOPool, User
from app.utils import encrypt_data
from flask import current_app, url_for

## User Flow Tests (Setup -> Login -> Settings)

def test_redirects_to_setup_on_first_run(client):
    """
    Test 1: Checks if a 'clean' application redirects to /setup.
    """
    response = client.get('/')
    assert response.status_code == 302 # We expect a redirect
    assert response.location == '/setup'

def test_setup_page_loads(client):
    """Test 2: Checks if the /setup page loads correctly."""
    response = client.get('/setup')
    # current_app.logger.info(f"response: {response}")
    # current_app.logger.info(f"response.location: {response.location}")
    # current_app.logger.info(f"response.data: {response.data}")
    assert response.status_code == 200
    assert b"Initial Administrator Setup" in response.data

def test_setup_creates_user_and_redirects(client):
    """Test 3: Checks if the /setup form creates a user and redirects to login."""
    assert User.query.count() == 0
    response = client.post('/setup', data={
        'username': 'admin',
        'password': 'secretpassword',
        'password2': 'secretpassword'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Admin account created successfully!" in response.data
    assert b"Sign In" in response.data # Check if we are on the login page
    assert User.query.count() == 1
    assert User.query.first().username == 'admin'

def test_login_redirects_to_settings_if_not_configured(auth_client):
    """
    Test 4: Checks if a logged-in user without a configured token
    is redirected to /settings.
    """
    response = auth_client.get('/')
    assert response.status_code == 302
    assert response.location == '/settings'
    
    # Also check if the settings page loads
    response_settings = auth_client.get('/settings')
    assert response_settings.status_code == 200
    assert b'Please configure the GitHub API Token' in response_settings.data

def test_index_loads_for_configured_user(configured_client):
    """
    Test 5: Checks if the main page (/) loads correctly for a logged-in
    and fully configured user.
    """
    response = configured_client.get('/')
    assert response.status_code == 200
    assert b"Self-Hosted Runners Monitoring" in response.data

## Functionality Tests for Logged-in User

def test_settings_are_protected(client):
    """Checks if the /settings page is protected against unauthenticated access."""
    response = client.get('/settings')
    assert response.status_code == 302 # Redirect to /setup or /login
    
def test_settings_post_github_settings(auth_client): # Using auth_client
    """Tests saving GitHub settings via POST request."""
    response = auth_client.post('/settings', data={
        'form_name': 'github',
        'active_tab': '#github',
        'org_name': 'new-test-org',
        'api_token': 'new-gh-token'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'GitHub Organization name has been saved.' in response.data
    assert b'GitHub API Token has been updated!' in response.data
    
    org = Setting.query.filter_by(key='ORGANIZATION').first()
    token = Setting.query.filter_by(key='API_GITHUB_TOKEN').first()
    assert org.value == 'new-test-org'
    assert token is not None # Check if the token exists

def test_settings_post_add_ado_organization(configured_client): # Using configured_client
    """Tests adding a new Azure DevOps configuration."""
    response = configured_client.post('/settings', data={
        'form_name': 'add_ado_org',
        'active_tab': '#ado',
        'organization_name': 'my-new-ado-org',
        'pat_token': 'new-pat-token'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'has been added successfully' in response.data
    config = AzureDevOpsConfig.query.filter_by(organization_name='my-new-ado-org').first()
    assert config is not None

def test_jira_confluence_status_page(configured_client, requests_mock): # Using configured_client
    """Tests the Jira & Confluence status page."""
    # Add settings within the test to make it independent
    db.session.add(Setting(key='JIRA_BASE_URL', value='https://test.atlassian.net'))
    db.session.add(Setting(key='JIRA_EMAIL', value='test@example.com'))
    db.session.add(Setting(key='JIRA_API_TOKEN', value=encrypt_data('fake-token')))
    db.session.commit()

    requests_mock.get('https://test.atlassian.net/status', json={'state': 'RUNNING'})
    requests_mock.get('https://test.atlassian.net/wiki/status', json={'state': 'DEGRADED'})

    response = configured_client.get('/jira-confluence')
    assert response.status_code == 200
    assert b'badge text-bg-success' in response.data
    assert b'badge text-bg-warning' in response.data

## API Tests (require a configured client)

def test_api_verify_ado_connection(configured_client, requests_mock):
    """Tests the ADO connection verification API endpoint."""
    encrypted_token = encrypt_data('valid-pat')
    config = AzureDevOpsConfig(id=1, organization_name='test-org', pat_token=encrypted_token)
    db.session.add(config)
    db.session.commit()

    requests_mock.get('https://dev.azure.com/test-org/_apis/projects?api-version=7.0', json={'value': []})
    
    response = configured_client.post('/api/azure-devops/1/verify')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'success'

def test_api_delete_ado_config(configured_client):
    """Tests deleting an ADO configuration."""
    config = AzureDevOpsConfig(id=1, organization_name='test-org', pat_token='valid-pat')
    db.session.add(config)
    db.session.commit()
    
    assert AzureDevOpsConfig.query.count() == 1
    
    response = configured_client.delete('/api/azure-devops/1')
    assert response.status_code == 200
    assert response.get_json()['message'] == 'Configuration deleted.'
    assert AzureDevOpsConfig.query.count() == 0

def test_version_endpoint(configured_client):
    """Tests the /version endpoint, which should always be accessible."""
    response = configured_client.get('/version')
    assert response.status_code == 200
    data = response.get_json()
    assert 'version' in data