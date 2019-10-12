import os

from flask import Flask, request, render_template
# from flask_sqlalchemy import SQLAlchemy

from env import Record, ret_session

ss = ret_session()

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ranking')
def ranking():
    group = request.args.get('group')
    style = request.args.get('style')
    distance = request.args.get('distance')

    records = ss.query(Record).all()

    return render_template('ranking.html', records = records[:10])

if __name__ == "__main__":
    if os.name == "nt": #ローカルの自機Windowsのとき
        app.run(debug=True)
    else:
        port = int(os.getenv("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
