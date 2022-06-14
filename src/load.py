from flask import Blueprint, request
from google.cloud import datastore
from src import constants
from src import auth

client = datastore.Client()
bp = Blueprint('load', __name__, url_prefix='/loads')


@bp.route('', methods=['POST', 'GET', 'PATCH', 'DELETE', 'PUT'])
def load_all():
    """ Loads get and post route. """
    # Check accept header for json
    if 'application/json' not in request.accept_mimetypes:
        error_message = {
            "Error": "Client must accept valid JSON"
        }
        return error_message, 406

    if request.method == 'POST':
        try:
            payload = auth.verify_jwt(request)
        except:
            return auth.verify_jwt(request)

        # In the event that all headers indicate JSON but the content is not formatted as JSON.
        try:
            content = request.get_json()
        except:
            error_message = {
                "Error": "Content must be sent as valid JSON"
            }
            return error_message, 415

        # If there are any missing attributes from the expected 3
        if len(content) < 3:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        try:
            # Readable dictionary for the data update
            load_data = {
                "volume": content["volume"],
                "item": content["item"],
                "creation_date": content["creation_date"],
                "carrier": None,
                "owner": payload["sub"]
            }
        except:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # None of the attributes are acceptable, therefore "missing"
        if not isinstance(content["item"], str) or not isinstance(content["creation_date"], str) or not isinstance(content["volume"], int):
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # Data validation minimum (No maximum needed)
        if len(content["item"]) < 1 or len(content["creation_date"]) < 1 or content["volume"] < 1:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        new_load = datastore.entity.Entity(key=client.key(constants.load))

        new_load.update(load_data)
        client.put(new_load)

        # Add in the additional post creation data (ID is None until the put is performed)
        load_data["id"] = new_load.key.id
        # Generating self on the fly - self is never stored
        load_data["self"] = request.base_url + "/" + str(new_load.key.id)
        return load_data, 201

    # Get all paginated
    elif request.method == 'GET':
        # If login valid, show specific owner's boats.
        #   Else, all boats in collection
        query = client.query(kind=constants.load)
        try:
            payload = auth.verify_jwt(request)

            # datastore query filtering
            # https://cloud.google.com/datastore/docs/concepts/queries#datastore-datastore-basic-query-python
            query.add_filter("owner", "=", payload["sub"])

        except:
            # If the verification jwt failed, then there won't be a filter applied to the query
            #   In this event, all boats are shown to the user and not the ones owned by the boat owner itself
            pass    # Therefore, pass

        # Pagination details
        query_limit = int(request.args.get('limit', '5'))
        query_offset = int(request.args.get('offset', '0'))

        load_iterator = query.fetch(limit=query_limit, offset=query_offset)
        pages = load_iterator.pages

        results = list(next(pages))

        # Get the total
        count_query = client.query(kind=constants.boats)
        count_results = len(list(count_query.fetch()))

        # Pagination token condition
        if load_iterator.next_page_token:
            next_offset = query_offset + query_limit
            next_url = request.base_url + "?limit=" + str(query_limit) + "&offset=" + str(next_offset)
        else:
            next_url = None

        # Create the data per the pages
        for entry in results:
            entry["id"] = entry.key.id
            entry["self"] = request.host_url + "loads/" + str(entry["id"])

            # Add in the boats self
            if entry["carrier"] is not None:
                entry["carrier"]["self"] = request.host_url + "boats/" + str(entry["carrier"]["id"])

        output = {"loads": results}

        if next_url:
            output["next"] = next_url

        output["total"] = count_results

        return output, 200

    else:   # Patch, Delete, Put
        error_message = {
            "Error": "Method not allowed"
        }
        return error_message, 405


@bp.route('/<load_id>', methods=['GET', 'DELETE', 'PATCH', 'PUT'])
def load_specific(load_id):
    """ Loads get and delete route."""
    # All GET, DELETE, PATCH, PUT methods are protected
    try:
        payload = auth.verify_jwt(request)
    except:
        return auth.verify_jwt(request)

    load_key = client.key(constants.load, int(load_id))
    load = client.get(key=load_key)

    # If no load is found per the key
    if load is None:
        error_message = {
            "Error": "No load with this load_id exists"
        }
        return error_message, 404

    # Check if this boat is indeed owned by the authenticator
    if load["owner"] != payload["sub"]:
        error_message = {
            "Error": "This load does not belong to you"
        }
        return error_message, 403

    # Check accept header for json
    if 'application/json' not in request.accept_mimetypes:
        error_message = {
            "Error": "Client must accept valid JSON"
        }
        return error_message, 406

    # Begin all methods
    if request.method == 'GET':
        # Generating self on the fly
        load["id"] = load.key.id
        load["self"] = request.base_url

        if load["carrier"] is not None:
            # Generating self on the fly
            load["carrier"]["self"] = request.host_url + "boats/" + str(load["carrier"]["id"])

        return load, 200

    elif request.method == 'DELETE':
        # Remove the load from a boat if existing
        if load["carrier"] is not None:
            boat_id = load["carrier"]["id"]

            boat_key = client.key(constants.boats, int(boat_id))
            boat = client.get(key=boat_key)

            # Because one load can be on a boat at a time, remove based on the singular index
            removal_idx = None
            for each_load in range(len(boat["loads"])):
                if boat["loads"][each_load]["id"] == int(load_id):
                    removal_idx = each_load

            # by popping it out of the list once found
            boat["loads"].pop(removal_idx)
            client.put(boat)

        client.delete(load_key)
        return '', 204

    elif request.method == 'PATCH':
        # Some data update
        # In the event that all headers indicate JSON but the content is not formatted as JSON.
        try:
            content = request.get_json()
        except:
            error_message = {
                "Error": "Content must be sent as valid JSON"
            }
            return error_message, 415

        # Verify all the required attributes are sent in.
        load_data = {}
        error_counter = 0

        try:
            load_data["item"] = content["item"]
            if not isinstance(content["item"], str) or len(content["item"]) < 1:
                error_message = {
                    "Error": "The request object is missing at least one of the required attributes"
                }
                return error_message, 400
        except:
            error_counter += 1
        try:
            load_data["creation_date"] = content["creation_date"]
            if not isinstance(content["creation_date"], str) or len(content["creation_date"]) < 1:
                error_message = {
                    "Error": "The request object is missing at least one of the required attributes"
                }
                return error_message, 400
        except:
            error_counter += 1
        try:
            load_data["volume"] = content["volume"]
            if not isinstance(content["volume"], int) or content["volume"] < 1:
                error_message = {
                    "Error": "The request object is missing at least one of the required attributes"
                }
                return error_message, 400
        except:
            error_counter += 1

            # In the event that the user never sent valid entries
        if error_counter >= 3:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # Update load
        load.update(load_data)
        client.put(load)

        # Add in the other details of load
        load["id"] = load.key.id
        # Generating self on the fly - self is never stored
        load["self"] = request.base_url
        return load, 200

    elif request.method == 'PUT':
        # All data update
        # In the event that all headers indicate JSON but the content is not formatted as JSON.
        try:
            content = request.get_json()
        except:
            error_message = {
                "Error": "Content must be sent as valid JSON"
            }
            return error_message, 415

        # If there are any missing attributes from the expected 3
        if len(content) < 3:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        try:
            # Readable dictionary for the data update
            load_data = {
                "volume": content["volume"],
                "item": content["item"],
                "creation_date": content["creation_date"],
            }
        except:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # None of the attributes are acceptable, therefore "missing"
        if not isinstance(content["item"], str) or not isinstance(content["creation_date"], str) or not isinstance(content["volume"], int):
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # Data validation minimum (No maximum needed)
        if len(content["item"]) < 1 or len(content["creation_date"]) < 1 or content["volume"] < 1:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # Update load
        load.update(load_data)
        client.put(load)

        # Add in other details of load
        load["id"] = load.key.id
        # Generating self on the fly - self is never stored
        load["self"] = request.base_url
        return load, 200

    else:   # Post
        error_message = {
            "Error": "Method not allowed"
        }
        return error_message, 405
