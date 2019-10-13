from flask import Flask

# 自分自身の名前をappという変数でインスタンス化
app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello World!'

# コマンドラインで本ファイルを起動させたときの動作
if __name__ == '__main__':
    # 安全のため debug=False とする
    # 特に本番稼働するファイルでは debug=True としてはいけない!
    app.run(debug=False)

# import datetime
# import json
# import os
# import re
# import requests
#
# from flask import Flask, request, render_template
# # from env import database_url
#
# app = Flask(__name__)
# app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False #これ書かないとログがうるさくなる
#
# # from models import db, Meet, Event, Record, RelayResult
#
#
# @app.route('/')
# def index():
#     return render_template('index.html')
#
#
# @app.route('/ranking')
# def ranking():
#     group = request.args.get('group')
#     style = request.args.get('style')
#     distance = request.args.get('distance')
#
#     # records = Record.query.all()
#
#     return render_template('ranking.html', records =[])
#
# if __name__ == "__main__":
#     if os.name == "nt": #ローカルの自機Windowsのとき
#         app.run(debug=True)
#     else:
#         port = int(os.getenv("PORT", 5000))
#         app.run(host="0.0.0.0", port=port, debug=False)
