# このモジュールはメイン関数から呼び出されることを前提に動く
# インポートされたあとメイン関数に再び戻る
# メイン関数におけるクエリ結果に対して使用するメソッドはここで定義される
# パーサーのためのメソッドはparser.pyで追加する
from __main__ import app
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy(app)

def create_table():
    db.create_all()

class Meet(db.Model):
    __tablename__ = 'meets'
    id = db.Column(db.Integer, primary_key=True)                      # 連番で振られるid
    meetid = db.Column(db.String, unique = True, nullable = False)    # 7桁の大会ID 0119721など0で始まることもある
    name = db.Column(db.String, nullable = False)                     # 大会名
    place = db.Column(db.String, nullable = False)                    # 会場
    pool = db.Column(db.String, nullable = False)                     # 短水路or長水路
    start = db.Column(db.String, nullable = False)                    # 大会開始日 2019/09/24 で表す
    end = db.Column(db.String, nullable = False)                      # 大会終了日
    area = db.Column(db.Integer, nullable = False)                    # 地域(整数2桁)
    year = db.Column(db.Integer, nullable = False)                    # 開催年(2桁)
    code = db.Column(db.Integer, nullable = False)                    # 下三桁

    def __str__(self):
        # return f'<{self.id}><{self.meetid}>{self.name} {self.pool} {self.start}'
        return str((self.id, self.meetid, self.name, self.pool, self.start))


class Record(db.Model): #個人種目の１記録
    __tablename__ = 'records'
    id = db.Column(db.Integer, primary_key=True)                      # 連番で振られるid
    meetid = db.Column(db.String, nullable = False)                   # 7桁の大会ID 0119721など0で始まることもある
    sex = db.Column(db.Integer, nullable = False)                     # 性別 {1:"男子", 2:"女子", 3:"混合"}
    style = db.Column(db.Integer, nullable = False)                   # 泳法 { 1:"自由形", 2:"背泳ぎ", 3:"平泳ぎ", 4:"バタフライ", 5:"個人メドレー", 6:"フリーリレー", 7:"メドレーリレー" }
    distance = db.Column(db.Integer, nullable = False)                # 距離 distances = { 1:"25m", 2:"50m", 3:"100m", 4:"200m", 5:"400m", 6:"800m", 7:"1500m" }
    name = db.Column(db.String, nullable = False)                     # 選手氏名
    team = db.Column(db.String, nullable = False)                     # 所属名
    grade = db.Column(db.String, nullable = False)                    # 学年 "中学3" "一般" 半角数字 スペースは消して格納
    time = db.Column(db.String, nullable = False)                     # タイム。#:##.##書式文字列
    laps = db.Column(db.String, nullable = False)                     # ラップタイム。#:##.##,#:##.##,...

    def __str__(self):
        # return f'<{self.id}><{self.meetid}>{self.sex}{self.style}{self.distance}:{self.name} {self.team} {self.grade} {self.time}'
        return str((self.id, self.meetid, self.sex, self.style, self.distance, self.name, self.team, self.grade, self.time))


class Relay(db.Model): #リレーの１記録
    __tablename__ = 'relays'
    id = db.Column(db.Integer, primary_key=True)                      # 連番で振られるid
    meetid = db.Column(db.String, nullable = False)                   # 7桁の大会ID 0119721など0で始まることもある
    sex = db.Column(db.Integer, nullable = False)                     # 性別
    style = db.Column(db.Integer, nullable = False)                   # 泳法
    distance = db.Column(db.Integer, nullable = False)                # 距離
    rank = db.Column(db.String, nullable = False)                     # 順位（棄権や失格の場合、順位にその旨記述される）
    team = db.Column(db.String, nullable = False)                     # 所属名
    time = db.Column(db.String, nullable = False)                     # 全体のタイム。#:##.##書式文字列 失格の場合はすべて空白文字列
    laps = db.Column(db.String, nullable = False)                     # ラップタイム。#:##.##,#:##.##,...
    name_1 = db.Column(db.String, nullable = False)                   # 第一泳者
    name_2 = db.Column(db.String, nullable = False)                   # 第二泳者
    name_3 = db.Column(db.String, nullable = False)                   # 第三泳者
    name_4 = db.Column(db.String, nullable = False)                   # 第四泳者
    grade_1 = db.Column(db.String, nullable = True)                   # 第一泳者の学年
    grade_2 = db.Column(db.String, nullable = True)                   # 第二泳者の学年
    grade_3 = db.Column(db.String, nullable = True)                   # 第三泳者の学年
    grade_4 = db.Column(db.String, nullable = True)                   # 第四泳者の学年
