from flask import Blueprint, request
from google.cloud import datastore
from src import constants

client = datastore.Client()
bp = Blueprint('users', __name__, url_prefix='/users')


@bp.route('', methods=['POST', 'GET', 'PATCH', 'DELETE', 'PUT'])
def users_get():
    """ Return all the users currently stored in the database"""
    # Check accept header for json
    if 'application/json' not in request.accept_mimetypes:
        error_message = {
            "Error": "Client must accept valid JSON"
        }
        return error_message, 406

    if request.method == 'GET':
        query = client.query(kind=constants.users)

        results = list(query.fetch())

        output = []
        for each_item in results:
            output.append({
                "id": each_item.key.id,
                "user_id": each_item["user_id"]
            })

        return {"users": output}, 200

    else:
        error_message = {
            "Error": "Method not allowed"
        }
        return error_message, 405
