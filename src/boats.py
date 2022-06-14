from flask import Blueprint, request
from google.cloud import datastore
from src import constants
from src import auth

client = datastore.Client()
bp = Blueprint('boats', __name__, url_prefix='/boats')


@bp.route('', methods=['POST', 'GET', 'PATCH', 'DELETE', 'PUT'])
def boats_all():
    """ Boats get and post route. """
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

        # If there are any missing attributes from the expected 3 - no need to assume extraneous attributes.
        if len(content) < 3:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        try:
            # Readable dictionary for the data update
            boat_data = {
                "name": content["name"],
                "type": content["type"],
                "length": content["length"],
                "loads": [],
                "owner": payload["sub"]
            }
        except:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # None of the attributes are acceptable, therefore "missing"
        if not isinstance(content["name"], str) or not isinstance(content["type"], str) or not isinstance(content["length"], int):
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # Data validation minimum (No maximum needed)
        if len(content["name"]) < 1 or len(content["type"]) < 1 or content["length"] < 1:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        new_boat = datastore.entity.Entity(key=client.key(constants.boats))

        new_boat.update(boat_data)
        client.put(new_boat)

        # Add in the additional post creation data (ID is None until the put is performed)
        boat_data["id"] = new_boat.key.id
        # Generating self on the fly - self is never stored
        boat_data["self"] = request.base_url + "/" + str(new_boat.key.id)
        return boat_data, 201

    # Get all paginated
    elif request.method == 'GET':
        # If login valid, show specific owner's boats.
        #   Else, all boats in collection
        query = client.query(kind=constants.boats)
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

        boat_iterator = query.fetch(limit=query_limit, offset=query_offset)
        pages = boat_iterator.pages

        results = list(next(pages))

        # Get the total
        count_query = client.query(kind=constants.boats)
        count_results = len(list(count_query.fetch()))

        # Pagination token condition
        if boat_iterator.next_page_token:
            next_offset = query_offset + query_limit
            next_url = request.base_url + "?limit=" + str(query_limit) + "&offset=" + str(next_offset)
        else:
            next_url = None

        # Create the data per the pages
        for entry in results:
            entry["id"] = entry.key.id
            entry["self"] = request.host_url + "boats/" + str(entry.key.id)

            # Add in the loads self
            if len(entry["loads"]) > 0:
                for each_load in entry["loads"]:
                    each_load["self"] = request.host_url + "loads/" + str(each_load["id"])

        output = {"boats": results}

        if next_url:
            output["next"] = next_url

        output["total"] = count_results

        return output, 200

    else:   # Patch, Delete, Put
        error_message = {
            "Error": "Method not allowed"
        }
        return error_message, 405


@bp.route('/<boat_id>', methods=['GET', 'DELETE', 'PATCH', 'PUT', 'POST'])
def boats_specific(boat_id):
    """ Boat id get and delete route. """
    # All GET, DELETE, PATCH, PUT methods are protected
    try:
        payload = auth.verify_jwt(request)
    except:
        return auth.verify_jwt(request)

    boat_key = client.key(constants.boats, int(boat_id))
    boat = client.get(key=boat_key)

    # If no boat is found per the key
    if boat is None:
        error_message = {
            "Error": "No boat with this boat_id exists"
        }
        return error_message, 404

    # Check if this boat is indeed owned by the authenticator
    if boat["owner"] != payload["sub"]:
        error_message = {
            "Error": "This boat does not belong to you"
        }
        return error_message, 403

    # Check accept header for json
    if 'application/json' not in request.accept_mimetypes:
        error_message = {
            "Error": "Client must accept valid JSON"
        }
        return error_message, 406

    # Begin all REST methods
    if request.method == "GET":
        # Generating self on the fly
        boat["id"] = boat.key.id
        boat["self"] = request.base_url

        if len(boat["loads"]) > 0:
            for each_load in boat["loads"]:
                # Generating self on the fly
                each_load["self"] = request.host_url + "loads/" + str(each_load["id"])

        return boat, 200

    elif request.method == 'DELETE':
        # Fix the load if deleting
        load_query = client.query(kind=constants.load)
        loads_results = list(load_query.fetch())

        # Set all load carriers to None
        for each_load in loads_results:
            if each_load["carrier"] is not None:
                if each_load["carrier"]["id"] == int(boat_id):
                    each_load["carrier"] = None
                    client.put(each_load)

        client.delete(boat_key)
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
        boat_data = {}
        error_counter = 0

        try:
            boat_data["name"] = content["name"]
            if not isinstance(content["name"], str) or len(content["name"]) < 1:
                error_message = {
                    "Error": "The request object is missing at least one of the required attributes"
                }
                return error_message, 400
        except:
            error_counter += 1
        try:
            boat_data["type"] = content["type"]
            if not isinstance(content["type"], str) or len(content["type"]) < 1:
                error_message = {
                    "Error": "The request object is missing at least one of the required attributes"
                }
                return error_message, 400
        except:
            error_counter += 1
        try:
            boat_data["length"] = content["length"]
            if not isinstance(content["length"], int) or content["length"] < 1:
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

        # Update boat
        boat.update(boat_data)
        client.put(boat)

        # Add in other details to boat
        boat["id"] = boat.key.id
        # Generating self on the fly - self is never stored
        boat["self"] = request.base_url
        return boat, 200

    elif request.method == 'PUT':
        # All
        # In the event that all headers indicate JSON but the content is not formatted as JSON.
        try:
            content = request.get_json()
        except:
            error_message = {
                "Error": "Content must be sent as valid JSON"
            }
            return error_message, 415

        if len(content) < 3:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        try:
            # Readable dictionary for the data update
            boat_data = {
                "name": content["name"],
                "type": content["type"],
                "length": content["length"],
            }
        except:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # None of the attributes are acceptable, therefore "missing"
        if not isinstance(content["name"], str) or not isinstance(content["type"], str) or not isinstance(content["length"], int):
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # Data validation minimum (No maximum needed)
        if len(content["name"]) < 1 or len(content["type"]) < 1 or content["length"] < 1:
            error_message = {
                "Error": "The request object is missing at least one of the required attributes"
            }
            return error_message, 400

        # Update boat
        boat.update(boat_data)
        client.put(boat)

        # Add in other details to boat
        boat["id"] = boat.key.id
        # Generating self on the fly - self is never stored
        boat["self"] = request.base_url

        return boat, 200

    else:   # Post
        error_message = {
            "Error": "Method not allowed"
        }
        return error_message, 405


@bp.route('/<boat_id>/loads/<load_id>', methods=['PUT', 'DELETE', 'GET', 'POST', 'PATCH'])
def add_delete_load(boat_id, load_id):
    """ Boat id add and delete load route."""
    # For both methods, all details are verified
    try:
        payload = auth.verify_jwt(request)
    except:
        return auth.verify_jwt(request)

    boat_key = client.key(constants.boats, int(boat_id))
    boat = client.get(key=boat_key)
    load_key = client.key(constants.load, int(load_id))
    load = client.get(key=load_key)

    # Only the boat owner can edit their own boats
    #   Boat owner can add any load
    if boat["owner"] != payload["sub"]:
        error_message = {
            "Error": "This boat does not belong to you"
        }
        return error_message, 403

    # If no load or boat are found per the key
    if boat is None or load is None:
        error_message = {
            "Error": "No boat with this boat_id is loaded with the load with this load_id"
        }
        return error_message, 404

    # Check accept header for json
    if 'application/json' not in request.accept_mimetypes:
        error_message = {
            "Error": "Client must accept valid JSON"
        }
        return error_message, 406

    # Begin boat loading/unloading changes
    if request.method == 'PUT':
        # If the boat already has a carrier
        if load["carrier"] is not None:
            error_message = {
                "Error": "The load is already loaded on another boat"
            }
            return error_message, 403

        # Add the load details
        add_load_data = {
            "id": load.id
        }

        # Stack on the loads
        if len(boat["loads"]) != 0:
            boat["loads"].append(add_load_data)
        else:
            boat["loads"] = [add_load_data]

        # Change the carrier
        new_load_carrier = {
            "id": int(boat_id)
        }

        load["carrier"] = new_load_carrier

        client.put(load)
        client.put(boat)  # Boat was updated directly via their keys
        return '', 204

    elif request.method == 'DELETE':
        # This boat is not actually loaded with anything
        if len(boat["loads"]) == 0:
            error_message = {
                "Error": "No boat with this boat_id is loaded with the load with this load_id"
            }
            return error_message, 404

        # Because one load can be on a boat at a time, remove based on the singular index
        removal_idx = None
        for each_load in range(len(boat["loads"])):
            if boat["loads"][each_load]["id"] == int(load_id):
                removal_idx = each_load

        # Pop from the list if there is a matching load id
        if removal_idx is not None:
            boat["loads"].pop(removal_idx)
        else:
            error_message = {
                "Error": "No boat with this boat_id is loaded with the load with this load_id"
            }
            return error_message, 404

        # Remove the carrier
        load["carrier"] = None

        client.put(load)
        client.put(boat)

        return '', 204

    else:   # Get, Post, Patch
        error_message = {
            "Error": "Method not allowed"
        }
        return error_message, 405
