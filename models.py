# このモジュールはメイン関数から呼び出されることを前提に動く
# インポートされたあとメイン関数に再び戻る
# メイン関数におけるクエリ結果に対して使用するメソッドはここで定義される
# パーサーのためのメソッドをparser.pyからインポートする
# from __main__ import app
import constant

import os
import re
import requests
from time import sleep

from bs4 import BeautifulSoup, element
from tqdm import tqdm

# from flask_sqlalchemy import SQLAlchemy
#
# # db = SQLAlchemy(app) #, session_options={"expire_on_commit": False})
# # db.init_app(app)
#
# # 以下がメインモジュールからimport appしないでdb接続をやる方式
# db = SQLAlchemy()
# def init(app):
#     global db
#     db.init_app(app)

print('models読み込み始め')
from app import db
print('appからdb')

meet_link_ptn = re.compile(r"code=[0-9]{7}$") # <a href="../../swims/ViewResult?h=V1000&amp;code=0119605"
meet_caption_ptn = re.compile(r"(.+)　（(.+)） (.水路)") # 茨城:第42回県高等学校春季　（取手ｸﾞﾘｰﾝｽﾎﾟｰﾂｾﾝﾀｰ） 長水路
event_link_ptn = re.compile(r"&code=(\d{7})&sex=(\d)&event=(\d)&distance=(\d)") # "/swims/ViewResult?h=V1100&code=0919601&sex=1&event=5&distance=4"
time_format_ptn = re.compile(r'([0-9]{0,2}):?([0-9]{2}).([0-9]{2})')

space_erase_table = str.maketrans("","","\n\r 　 ") # 第三引数に指定した文字が削除される。左から、LF,CR,半角スペース,全角スペース,nbsp
space_and_nums = str.maketrans("","","\n\r 　 1234.")

def del_space(str):
    return str.translate(space_erase_table) if str is not None else ""

def del_numspace(str):
    return str.translate(space_and_nums)

def format_time(time_str):
    if time_str == "" or time_str == "--:--.--" or time_str == "-": # リレーで第一泳者以外の失格の場合--:--.--になる
        return ""
    else:
        ob = re.match(time_format_ptn, time_str)
        if ob is None: # おそらく発生しないはず。すべて正規表現に一致するはず
            print('\n>>無効なタイム文字列:{}'.format(time_str))
            return time_str
        else:
            min = ob.group(1) if ob.group(1) != "" else 0 # 32.34とか分がないとき
            return "{}:{}.{}".format(min, ob.group(2), ob.group(3))

# DOM探索木をURLから生成
def pour_soup(url):
    sleep(0.8)
    req = requests.get(url)
    req.encoding = "cp932"
    return BeautifulSoup(req.text, "lxml")



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

    def __init__(self, meet_id): # meetidを受け取り大会情報を持たせる
        self.meetid = meet_id
        self.area = int(meet_id[:2])
        self.year = int(meet_id[2:4])
        self.code = int(meet_id[-2:])   # 下三桁
        soup = pour_soup(f"http://www.swim-record.com/swims/ViewResult/?h=V1000&code={meet_id}")
        caption = soup.find("div", class_ = "headder").find_all("td", class_ = "p14b")
        date = caption[0].string # 2019/04/27 - 2019/04/27  ←caption[0]
        self.start = date[:10]
        self.end = date[-10:]
        matchOb = re.match(meet_caption_ptn, caption[1].string) # 茨城:第42回県高等学校春季　（取手ｸﾞﾘｰﾝｽﾎﾟｰﾂｾﾝﾀｰ） 長水路  ←caption[1]
        self.name = matchOb.group(1)
        self.place = matchOb.group(2)
        self.pool = matchOb.group(3)


# これだけテーブルとして定義されない
class Event:
    def __init__(self, link):   # 一種目の情報とURL 1種目の結果一覧画面に紐付けられている
        matchOb = re.search(event_link_ptn, link) # link = "/swims/ViewResult?h=V1100&code=0919601&sex=1&event=5&distance=4"
        self.meet_id = matchOb.group(1)
        self.url = "http://www.swim-record.com" + link
        self.sex = int(matchOb.group(2))
        self.style = int(matchOb.group(3))
        self.distance = int(matchOb.group(4))

    def parse_table(self):
        soup = pour_soup(self.url)
        table = soup.find_all("tr", align = "center", bgcolor = False)       # 中央寄せで背景なしクラス指定なし= レコード行
        lap_tables = soup.find_all("tr", align = "right", id = True, style = True)# このtrは見出しも含むLAPSのテーブル全体
        return table, lap_tables



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

    def __init__(self, meet_id, sex, style, distance, row, lap_table):
        self.meetid = meet_id
        self.sex = sex
        self.style = style
        self.distance = distance
        data = row.find_all("td")
        self.name = data[1].string
        self.team = data[2].string
        self.grade = data[3].string
        self.time = data[4].a.string if data[4].a is not None else ""
        laps = lap_table.find_all("td", width = True)
        self.laps = [lap.string for lap in laps]

    def fix_raw_data(self):
        self.name = del_space(self.name)
        self.team = del_space(self.team)
        self.grade = del_space(self.grade)
        self.time = format_time(del_space(self.time))
        self.laps = ",".join([format_time(del_space(lap)) for lap in self.laps])


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

    def __init__(self, meet_id, sex, style, distance, row, lap_table):
        self.meetid = meet_id
        self.sex = sex
        self.style = style
        self.distance = distance
        data = row.find_all("td")
        self.rank = data[0].text # data[0].stringだとタグを含んだときにNoneが返されてしまう
        swimmers = [del_numspace(name) for name in data[1].contents if isinstance(name, element.NavigableString)] # data[1].contentsはbrタグを含む配列
        count_swimmers = len(swimmers)
        if count_swimmers !=4 and count_swimmers!=1: # おそらく発生しない
            print(data[1])
            raise IndexError("泳者が４人でも空白スペースだけでもありません！")
        self.name_1 = swimmers[0] if count_swimmers == 4 else ""
        self.name_2 = swimmers[1] if count_swimmers == 4 else ""
        self.name_3 = swimmers[2] if count_swimmers == 4 else ""
        self.name_4 = swimmers[3] if count_swimmers == 4 else ""
        self.team = data[2].string
        self.time = data[3].a.string if data[3].a is not None else ""
        laps = lap_table.find_all("td", width = True)
        self.laps = [lap.string for lap in laps]

    def fix_raw_data(self):
        self.rank = del_space(self.rank)
        self.team = del_space(self.team)
        self.time = format_time(del_space(self.time))
        self.laps = ",".join([format_time(del_space(lap)) for lap in self.laps])


# 大会のインスタンス集合から種目のインスタンス集合を作るサブルーチン
def arrange_events(target_meets_ids):
    events = []
    print(">>>{}の大会の全開催種目を集めています…".format(len(target_meets_ids)))
    for id in tqdm(target_meets_ids):
        soup = pour_soup(f"http://www.swim-record.com/swims/ViewResult/?h=V1000&code={id}")
        aTags = soup.find_all("a", class_=True)             # 100m自由形などへのリンク
        events.extend([Event(a["href"]) for a in aTags])    # リンクから種目のインスタンス生成
        print(">>>{}種目見つかりました。".format(len(events)))       # 25690 10min-1390meets
        return events


def fetch_records(target_meets_ids): # 対象の大会のインスタンス集合を受け取りそれらの記録すべて返す
    events = arrange_events(target_meets_ids)
    records = []
    print('>>>全種目の記録の抽出を開始します...')
    for e in tqdm(events):
        table, lap_tables = e.parse_table()
        if e.style <= 5: # 個人種目＝自由形・背泳ぎ・平泳ぎ・バタフライ・個人メドレー
            records.extend([Record(e.meet_id, e.sex, e.style, e.distance, row, lap_table) for row, lap_table in zip(table, lap_tables)])
        else:
            records.extend([Relay(e.meet_id, e.sex, e.style, e.distance, row, lap_table) for row, lap_table in zip(table, lap_tables)])
    print('>>>{}個の記録が見つかりました。\n>>>データを適切な形に編集しています...'.format(len(records)))
    for r in records:
        r.fix_raw_data()
    db.session.add_all(records)
    db.session.commit()
    print(f'>>>COMPLETE!! データ件数：{len(records)}')


# 特定の年度・地域で開催された大会IDのリストを作成するサブルーチン
def find_meet(year, area):
    url = r"http://www.swim-record.com/taikai/{}/{}.html".format(year, area)
    soup = pour_soup(url)
    #div内での一番最初のtableが競泳、そのなかでリンク先がコードになっているものを探す
    meet_id_aTags = soup.find("div", class_ = "result_main").find("table", recursive = False).find_all("a", href = meet_link_ptn)
    id_list = [a["href"][-7:] for a in meet_id_aTags] #大会コード七桁のみ抽出
    return id_list

def fetch_meets(year):
    print(f">>>20{year}年の大会IDを集めています…")
    meet_ids = []
    for area in tqdm(constant.area_list):
        meet_ids.extend(find_meet(year, area))

    print(f'>>>20{year}年に開催される{len(meet_ids)}の大会の情報を取得しています…')
    meets = [Meet(id) for id in tqdm(meet_ids)]
    db.session.add_all(meets)
    db.session.commit()
    print(f'>>>COMPLETE!! データ件数：{len(meets)}')
