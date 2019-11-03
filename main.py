# 循環importなんてするくらいならひとつのモジュールに統合させたほうがPythonらしいと思うんだ
import datetime
import os
import re
import requests
from time import sleep
import threading

from bs4 import BeautifulSoup, element
from flask import Flask, request, render_template
from flask_sqlalchemy import SQLAlchemy
import pandas as pd

from constant import style_dic, distance_dic, area_list
from format import del_space, del_numspace, format_time
from task_manager import Takenoko, free, busy, get_status


app = Flask(__name__)
if os.name == 'nt': # ローカルのWindows環境
    import env
    app.config.from_object('config.Develop')
else:
    app.config.from_object('config.Product')

db = SQLAlchemy(app)

manegement_url = os.environ['ADMIN_URL']
meet_link_ptn = re.compile(r"code=[0-9]{7}$")           # <a href="../../swims/ViewResult?h=V1000&amp;code=0119605"
meet_caption_ptn = re.compile(r"(.+)　（(.+)） (.水路)") # 茨城:第42回県高等学校春季　（取手ｸﾞﾘｰﾝｽﾎﾟｰﾂｾﾝﾀｰ） 長水路
event_link_ptn = re.compile(r"&code=(\d{7})&sex=(\d)&event=(\d)&distance=(\d)") # "/swims/ViewResult?h=V1100&code=0919601&sex=1&event=5&distance=4"

# DOM探索木をURLから生成
def pour_soup(url):
    sleep(0.4)
    req = requests.get(url)
    req.encoding = "cp932"
    return BeautifulSoup(req.text, "lxml")



class Meet(db.Model):
    __tablename__ = 'meets'
    id = db.Column(db.Integer, primary_key=True)                      # 連番で振られるid
    meetid = db.Column(db.String, unique = True, nullable = False)    # 7桁の大会ID 0119721など0で始まることもある
    name = db.Column(db.String, nullable = False)                     # 大会名
    place = db.Column(db.String, nullable = False)                    # 会場
    pool = db.Column(db.Integer, nullable = False)                    # 0 (短水路) or 1(長水路)
    start = db.Column(db.String, nullable = False)                    # 大会開始日 2019/09/24 で表す
    end = db.Column(db.String, nullable = False)                      # 大会終了日
    area = db.Column(db.Integer, nullable = False)                    # 地域(整数2桁)
    year = db.Column(db.Integer, nullable = False)                    # 開催年(2桁)
    code = db.Column(db.Integer, nullable = False)                    # 下三桁

    def __str__(self):
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
        self.pool = 0 if matchOb.group(3)=='短水路' else 1


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

    def export_tupple(self):
        return self.id, self.name, self.team, self.grade, self.time


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
        assert count_swimmers == 1 or count_swimmers == 4
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


def add_records(target_meets_ids): # 対象の大会のインスタンス集合を受け取りそれらの記録すべて返す
    """
    記録をテーブルに追加する。
    大会IDが格納されたリストを受け取り、１大会ごとにすべての記録を抽出し、RecordかRelayのインスタンスを生成する
    コミットするタイミングをどうするかが問題。最後にやるとメモリが開放されないかもしれないし、何回もやると途中で中断された場合に困る。
    """
    print(f">>> {len(target_meets_ids)}の大会の全記録の抽出開始")
    count_records = 0
    for id in Takenoko(target_meets_ids, 20):
        soup = pour_soup(f"http://www.swim-record.com/swims/ViewResult/?h=V1000&code={id}")
        aTags = soup.find_all("a", class_=True)             # 100m自由形などへのリンクをすべてリストに格納
        events = [Event(a["href"]) for a in aTags]          # リンクから種目のインスタンス生成
        for e in events:
            table, lap_tables = e.parse_table()
            set_args_4_records = [(e.meet_id, e.sex, e.style, e.distance, row, lap_table) for row, lap_table in zip(table, lap_tables)]
            if e.style <= 5: # 個人種目＝自由形・背泳ぎ・平泳ぎ・バタフライ・個人メドレー
                records = [Record(*args) for args in set_args_4_records]
            else:
                records = [Relay(*args) for args in set_args_4_records]
            count_records += len(records)
            for r in records:
                r.fix_raw_data()
            db.session.add_all(records)
            db.session.commit()
    print(f'>>> 全{count_records}の記録の保存が完了')
    free()


# 特定の年度・地域で開催された大会IDのリストを作成するサブルーチン
def find_meet(year, area):
    url = r"http://www.swim-record.com/taikai/{}/{}.html".format(year, area)
    soup = pour_soup(url)
    #div内での一番最初のtableが競泳、そのなかでリンク先がコードになっているものを探す
    meet_id_aTags = soup.find("div", class_ = "result_main").find("table", recursive = False).find_all("a", href = meet_link_ptn)
    id_list = [a["href"][-7:] for a in meet_id_aTags] #大会コード七桁のみ抽出
    return id_list

def add_meets(year):
    print(f">>> 20{year}年開催の大会IDの収集を開始")
    meet_ids = []
    for area in Takenoko(area_list):
        meet_ids.extend(find_meet(year, area))
    print(f'>>> 20{year}年に開催される全{len(meet_ids)}の大会情報を取得中')
    meets = [Meet(id) for id in Takenoko(meet_ids, 20)]
    db.session.add_all(meets)
    db.session.commit()
    print(f'>>> 全{len(meets)}の大会情報の保存が完了')
    free()


####### 以下ルーター #######
@app.route('/')
def index():
    count = db.session.query(Record).count()
    count += db.session.query(Relay).count()
    return render_template('index.html', count_records = count)

@app.route('/up')
def wake_up(): # 監視サービスで監視する用のURL
    return 'ok'

# TODO: リレーの記録も結合させる
@app.route('/ranking')
def ranking():
    pool = request.args.get('pool', 1, type=int)
    sex = request.args.get('sex', 1, type=int)
    style = style_dic[request.args.get('style', 'fr')]
    distance = distance_dic[request.args.get('distance', 50, type=int)]
    # 水路判定
    target_meets = db.session.query(Meet).filter_by(pool=pool).all()
    target_meets_ids = [m.meetid for m in target_meets]
    records = db.session.query(Record).filter(Record.meetid.in_(target_meets_ids), Record.time != "", Record.sex==sex, Record.style==style, Record.distance==distance).all()
    print(f'records length:{len(records)}')
    fixed = map(lambda x:x.export_tupple(), records)
    df = pd.DataFrame(fixed, columns = ['id', 'name', 'team', 'grade', 'time'])
    df.sort_values(['time'], inplace=True)
    df.drop_duplicates(subset=['name','grade'], inplace=True)
    # print(df)
    return render_template('ranking.html', records = df[:100], pool=pool, sex=sex, style=style, distance=distance)

@app.route(manegement_url) # commandなしのURLの場合、Noneが代入される
@app.route(manegement_url + '/<command>')
def manegement(command=None):

    if command == 'create':
        db.create_all()
        return 'すべてのテーブルを作成しました'

    elif command == 'drop':
        db.drop_all()
        return 'すべてのテーブルを削除しました'

    status = get_status()
    if command is None:
        thread_list = [t.name for t in threading.enumerate()] # 起動中のスレッド一覧を取得
        return f'<h1>{status}:{", ".join(thread_list)}</h1>'

    elif status == 'busy': #既に別のスクレイパーが動いているとき
        return f'<h1>Command Denied. One scraping process is runnnig.</h1><p>status: {status}</p>'

    elif command == 'meets':
        year = 19
        db.session.query(Meet).filter_by(year = year).delete() # 同じ年度を二重に登録しないように削除する
        th = threading.Thread(target=add_meets, name='scraper', args=(year,))

    elif command == 'records':
        range = request.args.get('range', default=None, type=int)
        if range is None:
            date_min = request.args.get('from', default="2019/04/01")
            date_max = request.args.get('to', default="2019/04/06")
        else:
            today = datetime.date.today()
            week_ago = today - datetime.timedelta(days=range)
            date_min = week_ago.strftime('%Y/%m/%d')
            date_max = today.strftime('%Y/%m/%d')
        print(f'from {date_min} to {date_max}')
        target_meets = db.session.query(Meet).filter(Meet.start >= date_min, Meet.start <= date_max).order_by(Meet.start).all()
        target_meets_ids = [m.meetid for m in target_meets]
        # リストでフィルターをかけているが、deleteの引数synchronize_sessionのデフォルト値'evaluate'ではこれをサポートしていない(らしい)からFalseを指定する
        db.session.query(Record).filter(Record.meetid.in_(target_meets_ids)).delete(synchronize_session = False)
        db.session.query(Relay).filter(Record.meetid.in_(target_meets_ids)).delete(synchronize_session = False)
        th = threading.Thread(target=add_records, name='scraper', args=(target_meets_ids,))

    else:
        return '<h1>invalid url</h1>'

    busy()
    th.start()
    db.session.commit()
    return '<h1>Commenced a scraping process</h1>'



if __name__ == "__main__": #gunicornで動かす場合は実行されない
    print('組み込みサーバーで起動します')
    app.run()
