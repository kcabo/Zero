import datetime

from flask import Flask, request, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests

import analyzer
from constant import FormatEvent, japanese_grades
from config import LINE_TOKEN

app = Flask(__name__)
# app.config.from_object('config.Develop')
app.config.from_object('config.Product') # 本番用
db = SQLAlchemy(app)

CURRENT_YEAR = 19

class Meet(db.Model):
    __tablename__ = 'meets'
    meet_id = db.Column(db.Integer, primary_key=True, autoincrement=False) # 7桁の大会ID 0119721など0で始まる場合は6桁になる
    meet_name = db.Column(db.String, nullable = False)
    place = db.Column(db.String, nullable = False)   # 会場
    pool = db.Column(db.Integer, nullable = False)   # 0 (短水路) or 1(長水路)
    start = db.Column(db.Integer, nullable = False)  # 大会開始日 20190924 の整数型で表す
    end = db.Column(db.Integer, nullable = False)    # 大会終了日
    area = db.Column(db.Integer, nullable = False)   # 地域(整数2桁)
    year = db.Column(db.Integer, nullable = False)   # 開催年(2桁)

class Record(db.Model): # 個人種目とリレーの記録
    __tablename__ = 'records'
    record_id = db.Column(db.Integer, primary_key=True)
    meet_id = db.Column(db.Integer, nullable = False)
    event = db.Column(db.Integer, nullable = False)   # 性別・スタイル・距離をつなげた整数
    relay = db.Column(db.Integer, nullable = False)   # 個人種目なら0、リレー一泳なら1,以後2,3,4泳。リレー全体記録なら5。
    rank = db.Column(db.String, nullable = False)     # 順位や棄権、失格情報など
    swimmer_id = db.Column(db.Integer, nullable = False)
    team_id = db.Column(db.Integer, nullable = False)
    time = db.Column(db.Integer, nullable = False)    # タイム。百倍秒数(hecto_seconds)。失格棄権は0。意味不明タイムは-1
    laps = db.Column(db.String, nullable = False)     # ラップタイム。百倍秒数をカンマでつなげる

class Swimmer(db.Model):
    __tablename__ = 'swimmers'
    swimmer_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable = False)
    sex = db.Column(db.Integer) # 1男子 2女子 3混合 0リレー
    awards = db.Column(db.Integer, default = 1)
    visits = db.Column(db.Integer, default = 0)
    read = db.Column(db.String)
    grade_17 = db.Column(db.Integer)
    grade_18 = db.Column(db.Integer)
    grade_19 = db.Column(db.Integer)
    grade_20 = db.Column(db.Integer)
    grade_21 = db.Column(db.Integer)

class Team(db.Model):
    __tablename__ = 'teams'
    team_id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String, nullable = False)
    area = db.Column(db.Integer)
    alias = db.Column(db.Integer) # 別名のチームID
    team_read = db.Column(db.String)

class Stats(db.Model): #種目の平均値、標準偏差
    __tablename__ = 'stats'
    stats_id = db.Column(db.Integer, primary_key=True)     # 自動で連番で振られるid
    pool = db.Column(db.Integer, nullable = False)         # 0 (短水路) or 1(長水路)
    event = db.Column(db.Integer, nullable = False)        # 性別・スタイル・距離をつなげた整数 25mも含める 混合は含めない
    grade = db.Column(db.Integer, nullable = False)        # 0 が全体 その後19まで各学年
    mean = db.Column(db.Float)                             # タイムの平均値 100倍秒数値
    std = db.Column(db.Float)                              # 標準偏差
    q1 = db.Column(db.Integer)                             # 第一四分位 百倍秒数。小さい、つまり速い方
    q2 = db.Column(db.Integer)                             # 第二四分位。中央値 百倍秒数
    q3 = db.Column(db.Integer)                             # 第三四分位 百倍秒数
    border = db.Column(db.Integer)                         # 500番目のタイム。百倍秒数
    count_agg = db.Column(db.Integer)                      # 現在の年度の全記録数
    count_ranking = db.Column(db.Integer)                  # 現在の年度のランキング人数


def calc_deviation(value, mean, std): # 無効の場合ハイフン
    if value and mean and std:
        answer = (value - mean) / std * -10 + 50 # 数値が少ないほうが高くしたいので－10かけ
        return round(answer, 1)
    else:
        return '-'

def count_records():
    count = session.query(func.count(Record.record_id)).scalar()
    return count

def notify_line(message):
    url = "https://notify-api.line.me/api/notify"
    print(message)
    if LINE_TOKEN:
        headers = {'Authorization': 'Bearer ' + LINE_TOKEN}
        payload = {'message': message, 'notificationDisabled': True}
        r = requests.post(url, headers=headers, params=payload)



####### 以下ルーター #######
@app.route('/')
def index():
    return render_template('index.html', count_records=count_records())

@app.route('/credits')
def credits():
    return render_template('credits.html')

@app.route('/develop')
def develop():
    return render_template('develop.html')

@app.route('/msg', methods = ['POST'])
def receive_message():
    msg = request.form.getlist("msg")[0]
    notify_line(msg)
    return render_template('index.html', count_records=total_count(), msg=msg)

@app.route('/up')
def wake_up(): # 監視サービスで監視する用のURL
    return 'ok'
    

@app.route('/ranking',  methods = ['POST', 'GET']) # 学年はPOST通信
def ranking():
    event = request.args.get('event', 112, type=int)
    year = request.args.get('year', 19, type=int)
    pool = request.args.get('pool', 1, type=int)
    all = request.args.get('all', 0, type=int)
    grades = request.form.getlist("grade", type=int) # POST時のフォームの内容が格納されるGET時は空リスト

    if grades: # 学年絞り込み指定ある時
        records = (db.session.query(Record, Meet)
                .filter(Record.event==event, Record.grade.in_(grades), Record.time > 0, Record.meetid == Meet.meetid, Meet.pool == pool, Meet.year == year)
                .all())
    elif all == 0: # もっとみる、を押す前
        target_event = db.session.query(Stats).filter_by(pool=pool, event=event, agegroup=0).one()
        time_limit = target_event.border
        records = (db.session.query(Record, Meet)
                .filter(Record.event==event, Record.time > 0, Record.time <= time_limit, Record.meetid == Meet.meetid, Meet.pool == pool, Meet.year == year)
                .all())
    else:
        records = (db.session.query(Record, Meet)
                .filter(Record.event==event, Record.time > 0, Record.meetid == Meet.meetid, Meet.pool == pool, Meet.year == year)
                .all())

    df = analyzer.format_ranking(analyzer.output_ranking(records))
    # {% for id, new, name, time, grade, grade_jp, team in ranking %}
    ranking = zip(df['id'], df['new'], df['name'], df['time'], df['grade'], df['grade_jp'], df['team'])
    my_event = FormatEvent(event)
    return render_template(
            'ranking.html',
            ranking = ranking,
            jpn_event = my_event.jpn_event(),
            year = year,
            sex = event // 100,
            pool = pool,
            style = event % 100,
            grades = grades,
            all = all)


@app.route('/dashboard')
def dashboard():
    # name と grade がついていることを保証している
    name = request.args.get('name')
    grade = request.args.get('grade', type=int)

    # 取得した選手の名前・学年でフィルタリングしてrecordsテーブルから取得
    # 同時にそれぞれのrecordのmeetidからMeetを内部結合 年度はとりま19年に指定
    records = (db.session.query(Record, Meet)
            .filter(Record.name == name, Record.grade == grade, Record.meetid == Meet.meetid, Meet.year == 19)
            .all())

    # 見出しの選手情報：     性別　名前　学年　所属一覧
    teams = {r.Record.team for r in records} # set型なので重複削除される
    sex = records[0].Record.event // 100 # ひとつめのレコードのeventの百の位
    swimmer = analyzer.Swimmer(records)
    del records # メモリ削減。効果ないかも
    swimmer.sex = 'men' if sex == 1 else 'women'
    swimmer.name = name
    swimmer.grade_jp = japanese_grades[grade]
    swimmer.grade = grade
    swimmer.teams = teams

    # 偏差値の導出
    event_code = swimmer.events[0].code
    if event_code:
        # 0全体・1小学・2中学・3高校・4大学・5一般
        agegroup_list = [0,1,1,1,1,1,1,2,2,2,3,3,3,4,4,4,4,4,4,5]
        agegroup = agegroup_list[grade] # gradeからagegroupへの変換 gradeは1以上なので最初の0が選ばれることはない
        stats = db.session.query(Stats).filter_by(event=event_code, agegroup=agegroup).order_by(Stats.pool).all() # 1番目が短水路、2番目が長水路になる
        dev_short = calc_deviation(swimmer.e1bests[0], stats[0].mean, stats[0].std)
        dev_long = calc_deviation(swimmer.e1bests[1], stats[1].mean, stats[1].std)
        deviation = dev_long if dev_long != '-' else dev_short
    else:
        deviation = '-'

    if deviation == '-':
        mask_height = 100
    elif deviation >= 75:
        mask_height = 0
    else:
        mask_height = 75 - deviation
    swimmer.deviation = deviation
    swimmer.mask_height = mask_height

    # バッジの格納
    icons = []
    if [True for t in teams if t in ['JPN', 'JAPAN', '日本']]:
        icons.append('fa-users')
    if [True for t in teams if t in ['慶應義塾大', 'KEIO', '慶應義塾大学', '慶応', '慶応女子', '慶應志木', '慶應', '慶應湘南藤沢', '慶應湘南', '慶應普通部', '銀泳会']]:
        icons.append('fa-pen-nib')
    if name == '神崎伶央':
        icons.append('fa-pastafarianism')
    if deviation >= 65:
        icons.append('fa-star')
    if deviation >= 70:
        icons.append('fa-chess-king')
    if swimmer.total_count >= 50:
        icons.append('fa-fist-raised')
    # <i class="fas fa-dragon"></i>
    swimmer.icons = icons

    return render_template('dashboard.html', s = swimmer)


@app.route('/search')
def search():
    query = request.args.get('query', '').replace(' ','').replace('_','').replace('%','')
    if query:
        records = db.session.query(Record).filter(Record.name.like(f"%{query}%"), Record.relay == 0).all()
        team_mates = db.session.query(Record).filter(Record.team.like(f"%{query}%"), Record.relay == 0).all()
        # team_matesは検索したチームから出た記録しか抽出されないので、各選手の他のチームから出た記録も検索
        names = {m.name for m in team_mates} # 検索したチームに所属する選手の他の所属を検索
        records_with_another_team = db.session.query(Record).filter(Record.name.in_(names), Record.relay == 0).all()
        records.extend(records_with_another_team)
        del records_with_another_team
    else:
        records = []

    men, women = analyzer.raise_candidates(records)
    show_sorry = False if men or women else True
    return render_template(
            'search.html',
            query = query,
            men = men,
            women = women,
            show_sorry = show_sorry)



@app.route('/apiResult', methods=['POST'])
def result_detail():
    body = request.get_json()
    id = body['id']
    target = db.session.query(Record, Meet).filter(Record.id==id, Record.meetid == Meet.meetid).first()
    res = analyzer.detail_dictionary(target)
    agegroup_list = [0,1,1,1,1,1,1,2,2,2,3,3,3,4,4,4,4,4,4,5] # 0全体・1小学・2中学・3高校・4大学・5一般
    agegroup = agegroup_list[target.Record.grade] # gradeからagegroupへの変換 gradeは1以上なので最初の0が選ばれることはない
    stats_agegroup = db.session.query(Stats).filter_by(event=target.Record.event, agegroup=agegroup, pool=target.Meet.pool).first()
    stats_whole = db.session.query(Stats).filter_by(event=target.Record.event, agegroup=0, pool=target.Meet.pool).first()
    res['dev1'] = calc_deviation(target.Record.time, stats_whole.mean, stats_whole.std)
    res['dev2'] = calc_deviation(target.Record.time, stats_agegroup.mean, stats_agegroup.std)
    return jsonify(res)


@app.route('/apiRank', methods=['POST'])
def time_and_rank():
    body = request.get_json()
    index = body['index']
    time_val = body['time_val']
    event = body['event_code']
    pool = body['pool']
    grade = body['grade']
    year = 19

    if event:
        target_stats = db.session.query(Stats).filter_by(event=event, agegroup=0, pool=pool).one()
        whole_count = target_stats.count
        same_count = (db.session.query(Record, Meet)
                .filter(Record.event == event, Record.time > 0, Record.grade == grade, Record.meetid == Meet.meetid, Meet.pool == pool, Meet.year == year)
                .distinct(Record.name)
                .count())
    else:
        whole_count = '-'
        same_count = '-'

    if time_val:
        # 自分より速いスイマーの数を数える
        whole_count_faster_swimmer = (db.session.query(Record, Meet)
                .filter(Record.event == event, Record.time > 0, Record.time < time_val, Record.meetid == Meet.meetid, Meet.pool == pool, Meet.year == year)
                .distinct(Record.name, Record.grade)
                .count())
        whole_ranking = whole_count_faster_swimmer + 1

        same_count_faster_swimmer = (db.session.query(Record, Meet)
                .filter(Record.event == event, Record.time > 0, Record.time < time_val, Record.grade == grade, Record.meetid == Meet.meetid, Meet.pool == pool, Meet.year == year)
                .distinct(Record.name)
                .count())
        same_ranking = same_count_faster_swimmer + 1

    else:
        whole_ranking = '-'
        same_ranking = '-'

    time = analyzer.val_2_fmt(time_val)

    rtn = {
        'index': index,
        'time': time if time else '-',
        'same_ranking': same_ranking,
        'same_count': same_count,
        'whole_ranking': whole_ranking,
        'whole_count': whole_count
    }
    return jsonify(rtn)





if __name__ == "__main__": #gunicornで動かす場合は実行されない
    print('組み込みサーバーで起動します')
    app.run()
