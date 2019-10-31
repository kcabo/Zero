import os

from flask import Flask, request, render_template

from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
if os.name == 'nt': # ローカルのWindows環境
    from env import database_url
else: # 本番Linux環境
    database_url = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False #これ書かないとログがうるさくなる


db = SQLAlchemy(app) #, session_options={"expire_on_commit": False})

print('頭 appが読み込まれた')

from views import *
print('views読み込み終わり')

if __name__ == "__main__":

    # import views

    if os.name == "nt": #ローカルの自機Windowsのとき
        print('ローカルで起動します')
        app.run(debug=True)
    else:
        print('本番環境で起動します')
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
