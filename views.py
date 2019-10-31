import datetime
import json
import os
import re
import requests
import threading
# from tqdm import tqdm

from flask import Flask, request, render_template

#
# app = Flask(__name__)
# if os.name == 'nt': # ローカルのWindows環境
#     from env import database_url
# else: # 本番Linux環境
#     database_url = os.environ['DATABASE_URL']
# app.config['SQLALCHEMY_DATABASE_URI'] = database_url
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False #これ書かないとログがうるさくなる
#
#
# from models import init
# # import models
# init(app)
from models import db, Meet, Record, Relay, fetch_meets, fetch_records

from app import app

@app.route('/')
def index():
    count = db.session.query(Record).count()
    return render_template('index.html', count_records = count)


@app.route('/ranking')
def ranking():
    group = request.args.get('group')
    style = request.args.get('style')
    distance = request.args.get('distance')
    records = db.session.query(Record).filter(Record.time != "").order_by(Record.time).limit(20)
    return render_template('ranking.html', records = records)


@app.route('/db/create')
def create():
    db.create_all()
    return 'CREATEDだぜやったね'

#ここ隠さないと他の人にアクセスされてしまう
@app.route('/db/drop')
def drop():
    db.drop_all()
    return 'DROPDROPざまあみろ'


@app.route('/scrape') # /scrapeだけのURLの場合、targetにNoneが代入されて実行される
@app.route('/scrape/<target>')
def start_scraper(target=None):
    thread_list = [t.name for t in threading.enumerate()]
    tasks_msg = f'ONGOING TASKS: {", ".join(thread_list)}'

    if target is None:
        return tasks_msg
    elif 'scraper' in thread_list: #既に別のスクレイパーが動いているとき
        return 'Command Denied. A scraping process is working already. ' + tasks_msg
    elif target == 'meets':
        year = 19
        db.session.query(Meet).filter_by(year = year).delete() # 同じ年度を二重に登録しないように削除する
        th = threading.Thread(target=fetch_meets, name='scraper', args=(year,))
    elif target == 'records':
        date_min = "2019/04/01"
        date_max = "2019/04/06"
        target_meets = db.session.query(Meet).filter(Meet.start >= date_min, Meet.start <= date_max).all()
        target_meets_ids = [m.meetid for m in target_meets]
        db.session.query(Record).filter(Record.meetid.in_(target_meets_ids)).delete(synchronize_session = False)
        th = threading.Thread(target=fetch_records, name='scraper', args=(target_meets_ids,))
    else:
        return 'Please specify the target.'

    th.start()
    db.session.commit()
    return 'Commenced a scraping process'



# if __name__ == "__main__":
#     if os.name == "nt": #ローカルの自機Windowsのとき
#         app.run(debug=True)
#     else:
#         app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
