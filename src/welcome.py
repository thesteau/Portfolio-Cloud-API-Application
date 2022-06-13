from flask import request, render_template, session, redirect, Blueprint
import requests
import json

bp = Blueprint('welcome', __name__)


@bp.route('/', methods=['GET', 'POST'])
def index():
    """ Generate users with welcome page.
        Note that the password only has an 8 character minimum
    """
    if request.method == "POST":

        email, password = request.form.get('email'), request.form.get('password')
        data = {
            'username': email,
            'password': password
        }

        if request.form["button"] == "register":
            requests.post(request.url_root + 'register', json=data)

        # Get form data and convert to JSON to be posted to the corresponding link
        login = requests.post(request.url_root + 'login', json=data)

        if 'error' in json.loads(login.text):
            # Invalid login
            return json.loads(login.text), 404

        login_id = json.loads(login.text)["id_token"]
        session["login_id"] = login_id

        return redirect(request.url_root + 'user-info')

    return render_template('welcome.html')
