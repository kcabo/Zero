import datetime
import json
import os
import re
import requests

from flask import Flask, request, render_template

app = Flask(__name__)
if os.name == 'nt': # ローカルのWindows環境
    from env import database_url
else: # 本番Linux環境
    database_url = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False #これ書かないとログがうるさくなる

from models import * # db, create_table
# from parser import Meet, Record, Relay, Event

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/ranking')
def ranking():
    group = request.args.get('group')
    style = request.args.get('style')
    distance = request.args.get('distance')
    records = list()
    # records = db.session.query(Hoge).distinct(Hoge.name).all()#.order_by(Hoge.time).all()

    return render_template('ranking.html', records = records)



if __name__ == "__main__":
    if os.name == "nt": #ローカルの自機Windowsのとき
        app.run(debug=True)
    else:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
