from flask import request, session, Blueprint, redirect, url_for
from google.cloud import datastore
import requests
import json
from six.moves.urllib.request import urlopen
from jose import jwt

from src import constants


client = datastore.Client()
bp = Blueprint('auth', __name__)


class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code


# Verify the JWT in the request's Authorization header
def verify_jwt(request):
    if 'Authorization' in request.headers:
        auth_header = request.headers['Authorization'].split()
        token = auth_header[1]
    else:
        raise AuthError({"code": "no auth header",
                         "description":
                             "Authorization header is missing"}, 401)

    jsonurl = urlopen("https://" + constants.domain + "/.well-known/jwks.json")
    jwks = json.loads(jsonurl.read())
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.JWTError:
        raise AuthError({"code": "invalid_header",
                         "description":
                             "Invalid header. "
                             "Use an RS256 signed JWT Access Token"}, 401)
    if unverified_header["alg"] == "HS256":
        raise AuthError({"code": "invalid_header",
                         "description":
                             "Invalid header. "
                             "Use an RS256 signed JWT Access Token"}, 401)
    rsa_key = {}
    for key in jwks["keys"]:
        if key["kid"] == unverified_header["kid"]:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"]
            }
    if rsa_key:
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=constants.algorithms,
                audience=constants.client_id,
                issuer="https://" + constants.domain + "/"
            )
        except jwt.ExpiredSignatureError:
            raise AuthError({"code": "token_expired",
                             "description": "token is expired"}, 401)
        except jwt.JWTClaimsError:
            raise AuthError({"code": "invalid_claims",
                             "description":
                                 "incorrect claims,"
                                 " please check the audience and issuer"}, 401)
        except Exception:
            raise AuthError({"code": "invalid_header",
                             "description":
                                 "Unable to parse authentication"
                                 " token."}, 401)

        return payload
    else:
        raise AuthError({"code": "no_rsa_key",
                         "description":
                             "No RSA key in JWKS"}, 401)


# Generate a JWT from the Auth0 domain and return it
# Request: JSON body with 2 properties with "username" and "password"
#       of a user registered with this Auth0 domain
# Response: JSON with the JWT as the value of the property id_token
@bp.route('/login', methods=['POST'])
def login_user():
    """ Login user.
        Note that the password only has an 8 character minimum
    """
    # Check accept header for json
    if 'application/json' not in request.accept_mimetypes:
        error_message = {
            "Error": "Client must accept valid JSON"
        }
        return error_message, 406
    content = request.get_json()
    username = content["username"]
    password = content["password"]
    body = {'grant_type': 'password',
            'username': username,
            'password': password,
            'client_id': constants.client_id,
            'client_secret': constants.client_secret
            }
    headers = {'content-type': 'application/json'}
    url = 'https://' + constants.domain + '/oauth/token'
    r = requests.post(url, json=body, headers=headers)

    # Add user to datastore if there is a valid login
    try:
        login_id = json.loads(r.text)["id_token"]
        header = {'Authorization': 'Bearer ' + login_id}  # Header contains the bearer token
        payload = requests.get(
            request.url_root + 'decode',
            headers=header
        )
        login_data = {
            "user_id": json.loads(payload.text)["sub"]
        }
        add_user_to_datastore(login_data)
    except:
        pass

    return r.text, 200, {'Content-Type': 'application/json'}


@bp.route('/register', methods=['POST'])
def register_user():
    """ Register users from welcome page.
        Code replicates the login page with details from the documentation.
        Note that the password only has an 8 character minimum
    """
    # Check accept header for json
    if 'application/json' not in request.accept_mimetypes:
        error_message = {
            "Error": "Client must accept valid JSON"
        }
        return error_message, 406
    # https://auth0.com/docs/api/authentication#signup
    content = request.get_json()
    username = content["username"]
    password = content["password"]
    body = {'grant_type': 'password',
            'email': username,
            'username': username,
            'password': password,
            'client_id': constants.client_id,
            'connection': 'Username-Password-Authentication'
            }
    headers = {'content-type': 'application/json'}
    url = 'https://' + constants.domain + '/dbconnections/signup'
    r = requests.post(url, json=body, headers=headers)

    # Add user to datastore if user does not exist but has a valid registration
    try:
        login_id = json.loads(r.text)["id_token"]
        header = {'Authorization': 'Bearer ' + login_id}  # Header contains the bearer token
        payload = requests.get(
            request.url_root + 'decode',
            headers=header
        )
        login_data = {
            "user_id": json.loads(payload.text)["sub"]
        }
        add_user_to_datastore(login_data)
    except:
        pass

    return r.text, 200, {'Content-Type': 'application/json'}


@bp.route('/user-info', methods=['GET'])
def show_user_jwt():
    """ User JWT info page generated as JSON"""
    try:
        login_id = session['login_id']
    except:
        # If the user came to this page without a login session, then they return to the welcome page.
        return redirect(url_for('welcome.index'))
    session.clear()
    header = {'Authorization': 'Bearer ' + login_id}  # Header contains the bearer token
    payload = requests.get(
        request.url_root + 'decode',
        headers=header
    )

    login_data = {
        "jwt_id_token": login_id,
        "user_id": json.loads(payload.text)["sub"]
    }

    # Add user to datastore if using the welcome page
    data_store_id = add_user_to_datastore(login_data)

    login_data["data_store_id"] = data_store_id

    return login_data


def add_user_to_datastore(login_data):
    """ Add user to the datastore as long as the id does not exist
        If already exists, consistent requests will not add the user as a new entry.
    """
    query = client.query(kind=constants.users)
    results = list(query.fetch())
    for each_id in results:
        if login_data["user_id"] == each_id["user_id"]:
            return each_id.key.id

    # Store the JWT information
    new_user = datastore.entity.Entity(key=client.key(constants.users))
    new_user.update(login_data)
    client.put(new_user)
    return new_user.key.id


# Decode the JWT supplied in the Authorization header
@bp.route('/decode', methods=['GET'])
def decode_jwt():
    payload = verify_jwt(request)
    return payload
