from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app, session
from flask_login import login_user, logout_user, current_user, login_required
from app.models import db, Setting, MonitoredGroup, AzureDevOpsConfig, MonitoredADOPool, User
from app.utils import encrypt_data, decrypt_data
from app.forms import LoginForm, SetupForm
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timezone
import json
import os
import time
import logging
from urllib.parse import urlsplit

api_cache = {}
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():

    refresh_interval = os.getenv('REFRESH_INTERVAL_SECONDS')
    return render_template(
        'index.html',
        refresh_interval=refresh_interval
    )
@main_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    
    logout_user()
    
    if User.query.first():
        return redirect(url_for('main.index'))

    form = SetupForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Admin account created successfully! Please log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('setup.html', title='Initial Setup', form=form)

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if not User.query.first():
        flash('No admin account has been set up yet. Please create one first.', 'warning')
        return redirect(url_for('main.setup'))

    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('main.login'))

        login_user(user, remember=True)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)

    return render_template('login.html', title='Sign In', form=form)

@main_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':

        form_name = request.form.get('form_name')
        active_tab_hash = request.form.get('active_tab', '#github')
        session['active_tab'] = active_tab_hash

        if form_name == 'github':
            new_token = request.form.get('api_token')
            org_name = request.form.get('org_name')
            if not org_name:
                flash('GitHub Organization name is required!', 'danger')
            else:
                update_or_create_setting('ORGANIZATION', org_name)
                flash('GitHub Organization name has been saved.', 'info')
            if new_token:
                update_or_create_setting('API_GITHUB_TOKEN', new_token)
                flash('GitHub API Token has been updated!', 'success')

        elif form_name == 'jira':
            jira_url = request.form.get('jira_base_url')
            jira_email = request.form.get('jira_email')
            jira_token = request.form.get('jira_api_token')
            update_or_create_setting('JIRA_BASE_URL', jira_url or '')
            update_or_create_setting('JIRA_EMAIL', jira_email or '')
            if jira_token:
                update_or_create_setting('JIRA_API_TOKEN', jira_token)
            flash('Jira & Confluence settings have been saved.', 'success')

        elif form_name == 'add_ado_org':
            org_name = request.form.get('organization_name')
            pat_token = request.form.get('pat_token')
            if org_name and pat_token:
                existing_config = AzureDevOpsConfig.query.filter_by(organization_name=org_name).first()
                if existing_config:
                    flash(f'An Azure DevOps configuration for organization "{org_name}" already exists.', 'warning')
                else:
                    encrypted_pat = encrypt_data(pat_token)
                    new_ado_config = AzureDevOpsConfig(organization_name=org_name, pat_token=encrypted_pat)
                    db.session.add(new_ado_config)
                    db.session.commit()
                    flash(f'Azure DevOps organization "{org_name}" has been added successfully.', 'success')
            else:
                flash('Both Organization Name and PAT Token are required.', 'danger')

        elif form_name == 'update_ado_org':
            config_id = request.form.get('config_id')
            new_pat_token = request.form.get('pat_token')
            if new_pat_token and config_id:
                config_to_update = db.session.get(AzureDevOpsConfig, int(config_id))
                if config_to_update:
                    config_to_update.pat_token = encrypt_data(new_pat_token)
                    db.session.commit()
                    flash(f'PAT Token for {config_to_update.organization_name} has been updated.', 'success')
                else:
                    flash('Configuration not found.', 'danger')
            else:
                flash('No new PAT token was provided to update.', 'info')
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Database error: {e}', 'danger')
        api_cache.clear()
        return redirect(url_for('main.settings'))

    active_tab = session.pop('active_tab', '#github')
    config = get_config_from_db()
    ado_configs = AzureDevOpsConfig.query.order_by(AzureDevOpsConfig.organization_name).all()

    return render_template('settings.html', config=config, ado_configs=ado_configs, active_tab=active_tab)

@main_bp.route('/jira-confluence')
def jira_confluence_status():
    logger = current_app.logger
    config = get_config_from_db()

    base_url = config.get('JIRA_BASE_URL')
    email = config.get('JIRA_EMAIL')
    encrypted_token = config.get('JIRA_API_TOKEN')
    token = decrypt_data(encrypted_token)

    if not all([base_url, email, token]):
        flash('Jira & Confluence integration is not fully configured. Please provide Base URL, Email, and API Token in settings.', 'warning')
        return render_template('jira_confluence_status.html', error="Configuration is incomplete.")

    headers = {'Accept': 'application/json'}
    auth = HTTPBasicAuth(email, token)
    
    jira_status = None
    confluence_status = None
    
    try:
        jira_url = f"{base_url.rstrip('/')}/status"
        logger.info(f"Checking Jira status at: {jira_url}")
        response = requests.get(jira_url, headers=headers, auth=auth, timeout=10, verify=False)
        response.raise_for_status()
        jira_status = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error checking Jira status: {e}")
        jira_status = {'error': str(e)}

    try:
        confluence_url = f"{base_url.rstrip('/')}/wiki/status"
        logger.info(f"Checking Confluence status at: {confluence_url}")
        response = requests.get(confluence_url, headers=headers, auth=auth, timeout=10, verify=False)
        response.raise_for_status()
        confluence_status = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error checking Confluence status: {e}")
        confluence_status = {'error': str(e)}

    return render_template('jira_confluence_status.html', jira=jira_status, confluence=confluence_status)

@main_bp.route('/api/azure-devops/<int:config_id>/verify', methods=['POST'])
def verify_ado_connection(config_id):
    config = db.get_or_404(AzureDevOpsConfig, config_id)
    decrypted_pat = decrypt_data(config.pat_token)
    auth = get_ado_api_auth(decrypted_pat)
    url = f"https://dev.azure.com/{config.organization_name}/_apis/projects?api-version=7.0"

    try:
        response = requests.get(url, auth=auth, timeout=10)
        if response.status_code == 200:
            return jsonify({'status': 'success', 'message': 'Connection successful!'})
        else:
            return jsonify({'status': 'error', 'message': f'Failed. Status code: {response.status_code}, Response: {response.text}'}), 400
    except requests.RequestException as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/api/azure-devops/<int:config_id>/pools', methods=['GET', 'POST'])
def handle_ado_pools(config_id):
    config = db.get_or_404(AzureDevOpsConfig, config_id)
    decrypted_pat = decrypt_data(config.pat_token)
    auth = get_ado_api_auth(decrypted_pat)
    url = f"https://dev.azure.com/{config.organization_name}/_apis/distributedtask/pools?api-version=7.0"

    if request.method == 'GET':
        try:
            response = requests.get(url, auth=auth, timeout=10)
            response.raise_for_status()
            all_pools = response.json().get('value', [])
            monitored_ids = {pool.pool_id for pool in config.monitored_pools}
            return jsonify({'available_pools': all_pools, 'monitored_ids': list(monitored_ids)})
        except requests.RequestException as e:
            return jsonify({'error': 'Failed to fetch agent pools', 'details': str(e)}), 500

    if request.method == 'POST':
        data = request.get_json()
        selected_pools = data.get('pools', [])
        
        MonitoredADOPool.query.filter_by(ado_config_id=config.id).delete()
        
        for pool_data in selected_pools:
            new_monitored_pool = MonitoredADOPool(
                pool_id=pool_data['id'],
                pool_name=pool_data['name'],
                ado_config_id=config.id
            )
            db.session.add(new_monitored_pool)
        
        db.session.commit()
        return jsonify({'message': 'Monitored agent pools have been updated.'})

@main_bp.route('/api/azure-devops/<int:config_id>', methods=['DELETE'])
def delete_ado_config(config_id):
    config = db.get_or_404(AzureDevOpsConfig, config_id)
    db.session.delete(config)
    db.session.commit()
    return jsonify({'message': 'Configuration deleted.'})

@main_bp.route('/api/azure-devops/dashboard-data')
def get_ado_dashboard_data():
    logger = logging.getLogger('gunicorn.error')
    ado_configs = AzureDevOpsConfig.query.all()
    organizations_data = []

    for config in ado_configs:
        decrypted_pat = decrypt_data(config.pat_token)
        auth = get_ado_api_auth(decrypted_pat)
        org_data = {
            'id': config.id,
            'name': config.organization_name,
            'pools': []
        }

        for monitored_pool in config.monitored_pools:
            pool_agents_url = (
                f"https://dev.azure.com/{config.organization_name}/_apis/distributedtask/"
                f"pools/{monitored_pool.pool_id}/agents?api-version=7.0"
            )
            pool_info = { 'id': monitored_pool.pool_id, 'name': monitored_pool.pool_name, 'agents_data': { 'total_count': 0, 'agents': [] } }
            
            try:
                logger.info(f"Fetching ADO agents list for pool: {monitored_pool.pool_name}")
                list_response = requests.get(pool_agents_url, auth=auth, timeout=10)
                list_response.raise_for_status()
                
                agents_list = list_response.json().get('value', [])
                enriched_agents_data = []

                for agent_summary in agents_list:
                    agent_id = agent_summary.get("id")
                    if not agent_id: continue

                    normalized_agent = _normalize_ado_agent(agent_summary)

                    detail_url = (
                        f"https://dev.azure.com/{config.organization_name}/_apis/distributedtask/"
                        f"pools/{monitored_pool.pool_id}/agents/{agent_id}"
                        f"?api-version=7.1&includeAssignedRequest=true"
                    )
                    
                    try:
                        detail_response = requests.get(detail_url, auth=auth, timeout=5)
                        detail_response.raise_for_status()
                        agent_full_details = detail_response.json()
                        normalized_agent['busy'] = 'assignedRequest' in agent_full_details

                    except requests.exceptions.RequestException as e:
                        logger.error(f"Could not fetch details for agent ID {agent_id}: {e}")
                        normalized_agent['busy'] = False 

                    enriched_agents_data.append(normalized_agent)

                pool_info['agents_data']['agents'] = enriched_agents_data
                pool_info['agents_data']['total_count'] = len(enriched_agents_data)

            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to get agents list for pool {monitored_pool.pool_name}: {e}")
                pool_info['error'] = 'Failed to fetch agent list'
            
            org_data['pools'].append(pool_info)
        
        organizations_data.append(org_data)
        
    return jsonify({"organizations": organizations_data})

@main_bp.route('/azure-devops')
def azure_devops_dashboard():
    ado_configs = AzureDevOpsConfig.query.all()
    dashboard_data = []

    for config in ado_configs:
        auth = get_ado_api_auth(config.pat_token)
        org_data = {
            'id': config.id,
            'name': config.organization_name,
            'pools': []
        }
        logger = current_app.logger
        for monitored_pool in config.monitored_pools:
            url = f"https://dev.azure.com/{config.organization_name}/_apis/distributedtask/pools/{monitored_pool.pool_id}/agents?includeCapabilities=false&api-version=7.0"
            logger.info(url)
            try:
                response = requests.get(url, auth=auth, timeout=10)
                response.raise_for_status()
                agents = response.json().get('value', [])
                org_data['pools'].append({
                    'name': monitored_pool.pool_name,
                    'agents': agents
                })
            except requests.RequestException as e:
                current_app.logger.error(f"Failed to get agents for pool {monitored_pool.pool_name}: {e}")
                org_data['pools'].append({
                    'name': monitored_pool.pool_name,
                    'error': 'Failed to fetch agents'
                })
        dashboard_data.append(org_data)

    return render_template('azure_devops_dashboard.html', organizations=dashboard_data)

@main_bp.route('/api/runner-groups', methods=['GET'])
def get_all_runner_groups():
    config = get_config_from_db()
    org_name = config.get('ORGANIZATION')
    if not org_name:
        return jsonify({"error": "Organization name is missing."}), 400

    url = f"https://api.github.com/orgs/{org_name}/actions/runner-groups"
    all_groups, error = make_paginated_github_api_call(url)

    if error:
        return jsonify({"error": "Unable to fetch groups from GitHub API", "details": error}), 500

    #Hack to include "GitHub Hosted Runners into our monitoring dashboard"
    if all_groups is not None:
        github_hosted_group = {"id": 0, "name": "GitHub Hosted Runners"}
        all_groups.append(github_hosted_group)

    monitored_ids = {group.id for group in MonitoredGroup.query.all()}

    return jsonify({"available_groups": all_groups or [], "monitored_ids": list(monitored_ids)})

@main_bp.route('/api/runner-groups', methods=['POST'])
def save_monitored_groups():
    data = request.get_json()
    group_ids = data.get('group_ids', [])

    try:
        MonitoredGroup.query.delete()

        for group_id, group_name in group_ids:
            new_group = MonitoredGroup(id=group_id, name=group_name)
            db.session.add(new_group)

        db.session.commit()
        return jsonify({"message": "Data has been saved"}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unable to save groups: {e}")
        return jsonify({"error": "Unable to save groups."}), 500

@main_bp.route('/api/dashboard-data')
def get_dashboard_data():
    config = get_config_from_db()
    org_name = config.get('ORGANIZATION')
    monitored_groups_from_db = MonitoredGroup.query.all()

    if not org_name:
        return jsonify({"error": "Organization has not been configured", "groups": []}), 400

    if not monitored_groups_from_db:
        return jsonify({"groups": []})

    dashboard_data = []

    for group in monitored_groups_from_db:
        raw_runners, error = (None, None)

        # Because of the GitHub API we must handle 3 types of requests
        # 1. For normal self-hosted runners: https://docs.github.com/en/rest/actions/self-hosted-runner-groups?apiVersion=2022-11-28#list-self-hosted-runners-in-a-group-for-an-organization
        # 2. For github-hosted runners assigned to self-hosted runner group: https://docs.github.com/en/rest/actions/self-hosted-runner-groups?apiVersion=2022-11-28#list-github-hosted-runners-in-a-group-for-an-organization
        # 3. For github-hosted runners assigned to the organization (we create a fake runner group called: GitHub Hosted Runners: id=0): https://docs.github.com/en/rest/actions/hosted-runners?apiVersion=2022-11-28#list-github-hosted-runners-for-an-organization
        if group.id == 0:
            url = f"https://api.github.com/orgs/{org_name}/actions/hosted-runners"
        elif group.name == "Premium Runners":
            url = f"https://api.github.com/orgs/{org_name}/actions/runner-groups/{group.id}/hosted-runners"
        else:
            url = f"https://api.github.com/orgs/{org_name}/actions/runner-groups/{group.id}/runners"

        raw_runners, error = make_paginated_github_api_call(url)

        group_runners_list = []
        if not error and raw_runners is not None:
            if group.name == "Premium Runners" or group.id == 0:
                group_runners_list = [
                    _map_github_hosted_runner(r) for r in raw_runners]
            else:
                group_runners_list = [
                    _map_self_hosted_runner(r) for r in raw_runners]

        dashboard_data.append({
            "group_id": group.id,
            "group_name": group.name,
            "runners_data": {
                "total_count": len(group_runners_list),
                "runners": group_runners_list
            }
        })

    return jsonify({"groups": dashboard_data})

@main_bp.route('/health')
def get_health():
    logger = current_app.logger
    logger.info('Performing comprehensive health check')

    config = get_config_from_db()
    health_status = {}

    logger.info("Checking GitHub Actions status...")
    gh_org_name = config.get('ORGANIZATION')
    gh_token = config.get('API_GITHUB_TOKEN')

    if gh_token and gh_org_name:
        try:
            headers = get_github_api_headers()
            request_url = f"https://api.github.com/orgs/{gh_org_name}/actions/runner-groups"
            response = requests.get(request_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            token_expiration_str = response.headers.get('github-authentication-token-expiration')
            token_expiration_date = datetime.strptime(token_expiration_str, "%Y-%m-%d %H:%M:%S %z")
            is_token_valid = token_expiration_date > datetime.now(timezone.utc)
            
            health_status['github'] = {
                "status": "ok",
                "token_is_valid": is_token_valid,
                "token_scope": response.headers.get('x-accepted-github-permissions'),
                "token_expiration_date": token_expiration_str
            }
        except Exception as e:
            logger.error(f"GitHub health check failed: {e}")
            health_status['github'] = {"status": "error", "reason": str(e)}
    else:
        health_status['github'] = {"status": "not_configured"}

    logger.info("Checking Jira & Confluence status...")
    jira_base_url = config.get('JIRA_BASE_URL')
    jira_email = config.get('JIRA_EMAIL')
    jira_token = config.get('JIRA_API_TOKEN')

    if all([jira_base_url, jira_email, jira_token]):
        auth = HTTPBasicAuth(jira_email, jira_token)
        headers = {'Accept': 'application/json'}

        try:
            jira_url = f"{jira_base_url.rstrip('/')}/status"
            response = requests.get(jira_url, headers=headers, auth=auth, timeout=10)
            response.raise_for_status()
            if response.json().get('state') == 'RUNNING':
                health_status['jira'] = {"status": "ok"}
            else:
                health_status['jira'] = {"status": "error", "reason": f"State: {response.json().get('state')}"}
        except Exception as e:
            logger.error(f"Jira health check failed: {e}")
            health_status['jira'] = {"status": "error", "reason": "Connection failed"}

        # try:
        #     confluence_url = f"{jira_base_url.rstrip('/')}/wiki/status"
        #     response = requests.get(confluence_url, headers=headers, auth=auth, timeout=10)
        #     response.raise_for_status()
        #     if response.json().get('state') == 'RUNNING':
        #         health_status['confluence'] = {"status": "ok"}
        #     else:
        #         health_status['confluence'] = {"status": "error", "reason": f"State: {response.json().get('state')}"}
        # except Exception as e:
        #     logger.error(f"Confluence health check failed: {e}")
        #     health_status['confluence'] = {"status": "error", "reason": "Connection failed"}
    else:
        health_status['jira'] = {"status": "not_configured"}
        # health_status['confluence'] = {"status": "not_configured"}

    logger.info("Checking Azure DevOps status...")
    ado_configs = AzureDevOpsConfig.query.all()
    
    if ado_configs:
        ado_statuses = []
        for ado_config in ado_configs:
            org_status = {"organization": ado_config.organization_name}
            try:
                auth = get_ado_api_auth(ado_config.pat_token)
                url = f"https://dev.azure.com/{ado_config.organization_name}/_apis/projects?api-version=7.0"
                response = requests.get(url, auth=auth, timeout=10)
                response.raise_for_status()
                org_status["status"] = "ok"
            except Exception as e:
                logger.error(f"Azure DevOps health check for {ado_config.organization_name} failed: {e}")
                org_status["status"] = "error"
                org_status["reason"] = "Connection failed or invalid token"
            ado_statuses.append(org_status)
        health_status['azure_devops'] = ado_statuses
    else:
        health_status['azure_devops'] = []

    return jsonify(health_status)

@main_bp.route('/version')
def get_version():
    logger = current_app.logger
    version = os.getenv('APP_VERSION', 'local-dev')

    logger.info(f"Current Application Version: {version}")
    return jsonify({"version": version})

@main_bp.route('/healthcheck')
def healthcheck_page():
    with current_app.test_client() as client:
        response = client.get('/health')
        health_json = response.get_json()
        pretty_json = json.dumps(health_json, indent=4)
        return render_template('healthcheck.html', health_data=pretty_json)

@main_bp.route('/changelog')
def changelog():
    return render_template('changelog.html')

@main_bp.route('/runners-queues')
def runner_queues():
    return render_template('runners-queues.html')

def update_or_create_setting(key, value):
    setting = Setting.query.filter_by(key=key).first()

    if key in ['API_GITHUB_TOKEN', 'JIRA_API_TOKEN'] and value:
        value_to_save = encrypt_data(value)
    else:
        value_to_save = value

    if setting:
        setting.value = value_to_save
    else:
        setting = Setting(key=key, value=value_to_save)
        db.session.add(setting)
    # db.session.commit()

def get_config_from_db():
    settings = Setting.query.all()
    return {setting.key: setting.value for setting in settings}

def get_github_api_headers():
    config = get_config_from_db()
    encrypted_token = config.get('API_GITHUB_TOKEN')
    if not encrypted_token:
        current_app.logger.error("GitHub API Token not found in DB")
        return None
    token = decrypt_data(encrypted_token)
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def make_paginated_github_api_call(url):
    logger = current_app.logger
    cache_duration = current_app.config.get('API_CACHE_SECONDS', 30)
    cache_key = f"paginated:{url}"
    current_time = time.time()

    if cache_key in api_cache and (current_time - api_cache[cache_key]['timestamp']) < cache_duration:
        logger.info(f"Returning data from cache for: {url}")
        return api_cache[cache_key]['data'], None

    headers = get_github_api_headers()
    if headers is None:
        return None, "Token is missing in config"

    all_results = []
    next_url = f"{url}?per_page=100"

    while next_url:
        try:
            logger.info(f"Iterating over page: {next_url}")
            response = requests.get(next_url, headers=headers)
            response.raise_for_status()
            json_response = response.json()

            items_on_page = []
            if isinstance(json_response, list):
                items_on_page = json_response
            elif isinstance(json_response, dict) and 'runners' in json_response:
                items_on_page = json_response['runners']
            elif isinstance(json_response, dict) and 'runner_groups' in json_response:
                items_on_page = json_response['runner_groups']

            all_results.extend(items_on_page)

            if 'Link' in response.headers:
                links = requests.utils.parse_header_links(
                    response.headers['Link'])
                next_url = None
                for link in links:
                    if link.get('rel') == 'next':
                        next_url = link['url']
                        break
            else:
                next_url = None
        except requests.exceptions.HTTPError as http_err:
            error_message = f"HTTP ERROR: {http_err}"
            logger.error(error_message)
            return None, error_message
        except Exception as e:
            error_message = f"Unexpected error occured: {e}"
            logger.error(error_message)
            return None, error_message

    api_cache[cache_key] = {'data': all_results, 'timestamp': current_time}
    return all_results, None

def _map_self_hosted_runner(api_runner):
    return {"id": api_runner.get("id"), "name": api_runner.get("name"), "status": api_runner.get("status"), "busy": api_runner.get("busy"), "type": "self-hosted"}

def _map_github_hosted_runner(api_runner):
    api_status = api_runner.get("status")
    is_online = api_status == "Ready"
    is_busy = not is_online
    return {"id": api_runner.get("id"), "name": api_runner.get("name"), "status": "online" if is_online else "offline", "busy": is_busy, "type": "github-hosted"}

def get_ado_api_auth(pat_token):
    return HTTPBasicAuth('', pat_token)

def _normalize_ado_agent(agent_data):
    return {
        "id": agent_data.get("id"),
        "name": agent_data.get("name"),
        "status": agent_data.get("status", "offline"),
        "enabled": agent_data.get("enabled", False)
    }
