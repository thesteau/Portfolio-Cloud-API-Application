# Steven Au

from flask import Flask, jsonify
from src import load, boats, auth, users, welcome

app = Flask(__name__)
app.register_blueprint(welcome.bp)
app.register_blueprint(users.bp)
app.register_blueprint(boats.bp)
app.register_blueprint(load.bp)
app.register_blueprint(auth.bp)

app.config['SECRET_KEY'] = 'someSecret493'


@app.errorhandler(auth.AuthError)
def handle_auth_error(ex):
    return jsonify(ex.error), ex.status_code


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
