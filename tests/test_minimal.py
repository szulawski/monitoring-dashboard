from flask import Flask, flash, redirect, url_for, get_flashed_messages

minimal_app = Flask(__name__)
minimal_app.config['TESTING'] = True
minimal_app.config['SECRET_KEY'] = 'minimal-secret-for-testing'

@minimal_app.route('/set-flash', methods=['POST'])
def set_flash():
    flash('This is a minimal test message.')
    return redirect(url_for('target'))

@minimal_app.route('/target')
def target():
    messages = get_flashed_messages()
    if messages:
        return f"Target page reached. Message: {messages[0]}"
    else:
        return "Target page reached. No message found."

def test_flash_in_pure_isolation():
    with minimal_app.test_client() as client:
        response_post = client.post('/set-flash')

        assert response_post.status_code == 302
        response_get = client.get(response_post.location)

        assert response_get.status_code == 200
        assert b'This is a minimal test message.' in response_get.data