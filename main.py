# 循環importなんてするくらいならひとつのモジュールに統合させたほうがPythonらしいと思うんだ
# とかいってもやっぱスクレイパーを分離させたい
import datetime
import os
import re
import requests
from time import sleep
import threading

from bs4 import BeautifulSoup, element
from flask import Flask, request, render_template
from flask_sqlalchemy import SQLAlchemy

if os.name == 'nt': # ローカルのWindows環境なら、環境変数をその都度設定
    import env
import analyzer
from constant import style_2_num, distance_2_num, area_list, style_2_japanese, foreign_teams, event_2_num
from format import del_space, del_numspace, format_time
from task_manager import Takenoko, free, busy, get_status, notify_line


app = Flask(__name__)
app.config.from_object('config.Develop' if os.name == 'nt' else 'config.Product')
db = SQLAlchemy(app)

manegement_url = os.environ['ADMIN_URL']
meet_link_ptn = re.compile(r"code=[0-9]{7}$")           # <a href="../../swims/ViewResult?h=V1000&amp;code=0119605"
meet_caption_ptn = re.compile(r"(.+)　（(.+)） (.水路)") # 茨城:第42回県高等学校春季　（取手ｸﾞﾘｰﾝｽﾎﾟｰﾂｾﾝﾀｰ） 長水路
event_link_ptn = re.compile(r"&code=(\d{7})&sex=(\d)&event=(\d)&distance=(\d)") # "/swims/ViewResult?h=V1100&code=0919601&sex=1&event=5&distance=4"

# DOM探索木をURLから生成
def pour_soup(url):
    sleep(1)
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


class Statistics(db.Model): #種目の平均値、標準偏差
    __tablename__ = 'statistics'
    id = db.Column(db.Integer, primary_key=True)                      # 連番で振られるid
    pool = db.Column(db.Integer, nullable = False)                    # 0 (短水路) or 1(長水路)
    sex = db.Column(db.Integer, nullable = False)                     # 性別
    style = db.Column(db.Integer, nullable = False)                   # 泳法
    distance = db.Column(db.Integer, nullable = False)                # 距離
    agegroup = db.Column(db.String, nullable = False)                 # 全体・小学・中学・高校・大学・一般
    average = db.Column(db.Float)                                     # タイムの平均値 100倍秒数値
    sd = db.Column(db.Float)                                          # 標準偏差    100倍秒数値
    max500th = db.Column(db.String)                                   # 500番目のタイム。#:##.##書式文字列
    max5000th = db.Column(db.String)                                  # 5000番目のタイム。#:##.##書式文字列 設定しないかも
    count = db.Column(db.Integer)                                     # その種目のランキング化したあとの人数

    def __init__(self, pool, sex, style, distance, agegroup):
        self.pool = pool
        self.sex = sex
        self.style = style
        self.distance = distance
        self.agegroup = agegroup


def initialize_stats_table():
    for pool in [0, 1]:
        for sex in [1, 2]:
            for style in [1, 2, 3, 4, 5]:
                if style == 1: # Fr
                    distances = [2, 3, 4, 5, 6, 7]
                elif style == 5: # IM
                    distances = [3, 4, 5]
                else: # それ以外
                    distances = [2, 3, 4]

                for distance in distances:
                    for agegroup in ['全体', '一般', '大学', '高校', '中学', '小学']:
                        row = Statistics(pool, sex, style, distance, agegroup)
                        db.session.add(row)
    db.session.commit()


def set_standards():
    # statisticsテーブルの行を一行ずつ見ていき、それぞれアップデート
    stats = db.session.query(Statistics).all()
    for st in Takenoko(stats):
        records = (db.session.query(Record, Meet)
            .filter(Record.sex==st.sex, Record.style==st.style, Record.distance==st.distance, Record.time != "", Record.meetid == Meet.meetid, Meet.pool == st.pool)
            .all())
        st.average, st.sd, st.max500th, st.max5000th, st.count = analyzer.compile_statistics(records, st.agegroup)
    db.session.commit()
    free()

def calc_deviation(value, average, sd):
    res = (value - average) / sd * -10 + 50 #数値が少ないほうが高くしたいので－10かけ
    return round(res, 1)


def add_records(target_meets_ids): # 対象の大会のインスタンス集合を受け取りそれらの記録すべて返す
    """
    記録をテーブルに追加する。
    大会IDが格納されたリストを受け取り、１大会ごとにすべての記録を抽出し、RecordかRelayのインスタンスを生成する
    """
    initial_msg = f">>> {len(target_meets_ids)}の大会の全記録の抽出開始"
    notify_line(initial_msg)
    print(initial_msg)
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

    complete_msg = f'>>> 全{count_records}の記録の保存が完了'
    notify_line(complete_msg)
    print(complete_msg)
    free()


# 特定の年度・地域で開催された大会IDのリストを作成するサブルーチン
def find_meet(year, area):
    url = f"http://www.swim-record.com/taikai/{year}/{area}.html"
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
    return render_template('index.html', count_records=count)

@app.route('/up')
def wake_up(): # 監視サービスで監視する用のURL
    return 'ok'


@app.route('/dashboard', methods = ['POST', 'GET'])
def dashboard():
    if request.method == 'GET':
        id = request.args.get('id', 1, type=int)
        target = db.session.query(Record).get(id)
    else:
        search_name = request.form.get('name', '神崎伶央')
        target = db.session.query(Record).filter(Record.name == search_name).first()
        if target is None:
            return 'NO RESULTS'

    sex = target.sex
    name = target.name
    grade = target.grade

    # 取得した選手の性別・名前・学年でフィルタリングしてrecordsテーブルから取得
    # 同時にそれぞれのrecordのmeetidからMeetを内部結合
    records = (db.session.query(Record, Meet)
            .filter(Record.sex == sex, Record.name == name, Record.grade == grade, Record.meetid == Meet.meetid)
            .all())

    # 見出しの選手情報：     性別　名前　学年　所属(複数ある)
    teams = {r.Record.team for r in records}
    swimmer = analyzer.swimmer_statisctics(records)
    swimmer.sex = 'men' if sex == 1 else 'women'
    swimmer.name = name
    swimmer.grade = grade
    swimmer.teams = teams

    # S1偏差値の導出
    s1_style = event_2_num[swimmer.s1]['style']
    s1_distance = event_2_num[swimmer.s1]['distance']
    stats = db.session.query(Statistics).filter_by(sex=sex, style=s1_style, distance=s1_distance, agegroup=grade[:2]).order_by(Statistics.pool).all() # 1番目が短水路、2番目が長水路になる
    swimmer.dev_short = calc_deviation(swimmer.s1_best_short, stats[0].average, stats[0].sd) if swimmer.s1_best_short is not None else '-'
    swimmer.dev_long = calc_deviation(swimmer.s1_best_long, stats[1].average, stats[1].sd) if swimmer.s1_best_long is not None else '-'

    return render_template('dashboard.html', s = swimmer)

# TODO: リレーの記録も結合させる
@app.route('/ranking')
def ranking():
    pool = request.args.get('pool', 1, type=int)
    sex = request.args.get('sex', 1, type=int)
    style = request.args.get('style', 'Fr')
    distance = request.args.get('distance', 50, type=int)
    page = request.args.get('page', 1, type=int)

    records = (db.session.query(Record, Meet)
            .filter(Record.sex==sex, Record.style==style_2_num[style], Record.distance==distance_2_num[distance], Record.time != "", Record.meetid == Meet.meetid, Meet.pool == pool)
            .all()) # sortはORM側でやるのが早いのかそれともpandasに渡してからやったほうが早いのか…

    df_ = analyzer.output_ranking(records)
    print(f'query: all:{len(records)} filtered:{len(df_)} sex:{sex} pool:{pool} style:{style} distance:{distance}')
    data_from = 500*(page-1)
    data_till = 500*page
    df = df_[data_from:data_till] # 1ページ目なら[0:500]
    # {% for rank, id, name, time, grade, team in ranking %}
    ranking = zip(range(data_from+1, data_till+1), df['id'], df['name'], df['time'], df['grade'], df['team'])

    pages = ['hidden' if page==1 else page-1,
            'hidden' if len(df) < 500 else page+1]

    group = f'pool={pool}&sex={sex}'
    group_bools = [' selected' if pool==0 and sex==1 else '',
                ' selected' if pool==1 and sex==1 else '',
                ' selected' if pool==0 and sex==2 else '',
                ' selected' if pool==1 and sex==2 else '']
    current_event = f'style={style}&distance={distance}'
    str_sex = 'men' if sex == 1 else 'women'
    caption = f'{distance}m {style_2_japanese[style]}'

    return render_template(
            'ranking.html',
            ranking = ranking,
            group = group,
            group_bools = group_bools,
            current_event = current_event,
            caption = caption,
            str_sex = str_sex,
            pages = pages)

@app.route(manegement_url) # commandなしのURLの場合、Noneが代入される
@app.route(manegement_url + '/<command>')
def manegement(command=None):

    if command == 'create':
        db.create_all()
        return 'すべてのテーブルを作成しました'

    elif command == 'drop':
        db.drop_all()
        return 'すべてのテーブルを削除しました'

    elif command == 'deleteForeign':
        count = db.session.query(Record).filter(Record.team.in_(foreign_teams)).count()
        db.session.query(Record).filter(Record.team.in_(foreign_teams)).delete(synchronize_session = False)
        db.session.commit()
        return f'外国人チームの記録を削除。件数：{count}'

    elif command == 'initStats':
        db.session.query(Statistics).delete()
        initialize_stats_table()
        return '統計テーブルの初期化を完了'

    # ここから先は並列処理のコマンドになる
    status = get_status()
    if command is None:
        thread_list = [t.name for t in threading.enumerate()] # 起動中のスレッド一覧を取得
        return f'<h1>{status}:{", ".join(thread_list)}</h1>'

    elif status == 'busy': #既に別のジョブが動いているとき
        return f'<h1>Command Denied. One process is runnnig.</h1><p>status: {status}</p>'

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

    elif command == 'statistics':
        th = threading.Thread(target=set_standards, name='analyzer')

    else:
        return '<h1>invalid url</h1>'

    busy()
    db.session.commit()
    th.start()
    return '<h1>process started</h1>'




if __name__ == "__main__": #gunicornで動かす場合は実行されない
    print('組み込みサーバーで起動します')
    app.run()
