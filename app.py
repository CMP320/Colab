from flask import render_template, Flask, url_for
import cx_Oracle

app = Flask(__name__)

@app.route('/login')
@app.route('/')
def login():
    return render_template('login.html')