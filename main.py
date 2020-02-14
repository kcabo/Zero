import datetime

from flask import Flask, request, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import aliased
from sqlalchemy import func, desc, or_
import redis
import requests

import analyzer
from constant import FormatEvent, japanese_grades
from config import LINE_TOKEN, REDIS_URL, ADMIN_URL

app = Flask(__name__)
# app.config.from_object('config.Develop')
app.config.from_object('config.Product') # 本番用
db = SQLAlchemy(app)

r = redis.from_url(REDIS_URL, decode_responses=True)

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

def deviation(time, pool, event, grade):
    if time and event:
        pop = db.session.query(Stats.mean, Stats.std).filter_by(pool=pool, event=event, grade=grade).one()
        return calc_deviation(time, pop.mean, pop.std)
    else:
        return '-'



def notify_line(message, notify_disabled=True):
    url = "https://notify-api.line.me/api/notify"
    print(message)
    if LINE_TOKEN:
        headers = {'Authorization': 'Bearer ' + LINE_TOKEN}
        payload = {'message': message, 'notificationDisabled': notify_disabled}
        r = requests.post(url, headers=headers, params=payload)

def set_conditions(pool, event, year=None, grades=None, time_limit=None):
    # query内で使用する条件文のリスト
    conditions = [
        Record.meet_id == Meet.meet_id,
        Record.swimmer_id == Swimmer.swimmer_id,
        Record.team_id == Team.team_id,
        Meet.pool == pool,
        Record.event == event,
        Record.time > 0
    ]
    if year:
        conditions.append(Meet.year == year)
        if grades:  # grade0のときは全学年検索
            conditions.append(getattr(Swimmer, f'grade_{year}').in_(grades))
    if time_limit:
        conditions.append(Record.time <= time_limit)

    return conditions


####### 以下ルーター #######
@app.route('/')
def index():
    count_race, count_swimmer, count_meet = get_rows_count()
    return render_template(
            'index.html',
            count_race = count_race,
            count_swimmer = count_swimmer,
            count_meet = count_meet,
        )

@app.route('/credits')
def credits():
    return render_template('credits.html')

@app.route('/develop')
def develop():
    return render_template('develop.html')

@app.route('/msg', methods = ['POST'])
def receive_message():
    msg = request.form.getlist("msg")[0]
    notify_line('<ユーザーからのメッセージ>' + msg, False)
    return render_template('thank.html')

@app.route('/default')
def default():
    return render_template('default.html')


@app.route('/ranking',  methods = ['POST', 'GET']) # 学年はPOST通信
def ranking():
    pool = request.args.get('pool', 1, type=int)
    event = request.args.get('event', 0, type=int)
    year = request.args.get('year', CURRENT_YEAR, type=int)
    grades = request.form.getlist("grade", type=int) # POST時のフォームの内容が格納されるGET時は空リスト
    page = 1

    if event == 0: #旧ランキングページのURLから来たとき
        return index()

    time_limit = None
    if len(grades) == 0 and page == 1: # 2ページ目以降考えてない
        target_event = db.session.query(Stats.border).filter_by(pool=pool, event=event, grade=0).one()
        time_limit = target_event.border

    conditions = set_conditions(pool, event, year, grades, time_limit)
    stmt = db.session.query(
            Record.record_id,
            Swimmer.swimmer_id,
            Swimmer.name,
            getattr(Swimmer, f'grade_{year}'),
            Team.team_name,
            Record.time,
            Meet.start
        ).distinct(
            Record.swimmer_id
        ).filter(
            *conditions
        ).order_by(
            Record.swimmer_id,
            Record.time
        ).subquery()

    subq = aliased(Record, stmt)
    ranking_raw = db.session.query(stmt).order_by(subq.time).limit(500).all()
    ranking = analyzer.setup_ranking(ranking_raw, year)
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
        )

def unique_teams(team_ids):
    teams = db.session.query(Team.team_name).filter(Team.team_id.in_(team_ids)).order_by(Team.team_name).all()
    return [x.team_name for x in teams]

@app.route('/dashboard')
def dashboard():
    swimmer_id = request.args.get('s_id', None, type=int)
    if swimmer_id is None: #旧ページのURLから来たとき
        return index()

    year = CURRENT_YEAR
    records = db.session.query(
                Record.record_id,
                Record.event,
                Record.time,
                Record.team_id,
                Meet.pool,
                Meet.start,
                Meet.meet_name,
                Meet.year,
            ).filter(
                Record.meet_id == Meet.meet_id,
                Record.swimmer_id == swimmer_id,
            ).order_by(
                desc(Meet.start),
                Record.event,
                Record.time
            ).all()

    teams = unique_teams({r.team_id for r in records})
    profile = analyzer.Profile(records)

    target = db.session.query(Swimmer).get(swimmer_id)
    target.visits += 1
    db.session.commit()

    # 見出しの選手情報：     性別　名前　学年　所属一覧
    profile.sex = 'men' if target.sex == 1 else 'women'
    profile.name = target.name
    grade = getattr(target, f'grade_{year}')
    if grade is None:
        grade = 0
    profile.grade = grade
    profile.grade_jp = japanese_grades[grade]
    profile.teams = teams

    # 偏差値の導出
    profile.args.append(grade)
    dev = deviation(*profile.args)
    if dev == '-':
        mask_height = 100
    elif dev >= 75:
        mask_height = 0
    else:
        mask_height = 75 - dev
    profile.deviation = dev
    profile.mask_height = mask_height

    # バッジの格納
    icons = []
    if [True for t in teams if t in ['JPN', 'JAPAN', '日本']]:
        icons.append('fa-dragon')
    if [True for t in teams if t in ['慶應義塾大', 'KEIO', '慶應義塾大学', '慶応', '慶応女子', '慶應志木', '慶應', '慶應湘南藤沢', '慶應湘南', '慶應普通部', '銀泳会']]:
        icons.append('fa-pen-nib')
    if target.awards % 7 == 0:
        icons.append('fa-user-secret')
        icons.append('fa-user-secret')
        icons.append('fa-user-secret')
    if dev != '-' and dev >= 65:
        icons.append('fa-star')
        if dev >= 70:
            icons.append('fa-chess-king')
    if profile.total_count >= 50:
        icons.append('fa-fist-raised')
    profile.icons = icons

    return render_template('dashboard.html', s = profile)


@app.route('/search')
def search():
    query = request.args.get('q', '').replace(' ','').replace('_','').replace('%','')

    if query:
        swimmer_ids = db.session.query(Swimmer.swimmer_id).filter(Swimmer.name.like(f"%{query}%")).all()
        team_ids = db.session.query(Team.team_id).filter(Team.team_name.like(f"%{query}%")).all()
        records = db.session.query(
                    Swimmer.swimmer_id,
                    Swimmer.sex,
                    Swimmer.name,
                    Swimmer.grade_19,
                    Team.team_name
                ).distinct(
                    Record.swimmer_id,
                    Record.team_id
                ).filter(
                    Record.swimmer_id == Swimmer.swimmer_id,
                    Record.team_id == Team.team_id,
                    Record.relay == 0,
                    Swimmer.grade_19 != None,
                    or_(
                        Record.swimmer_id.in_([s.swimmer_id for s in swimmer_ids]),
                        Record.team_id.in_([t.team_id for t in team_ids])
                    )
                ).limit(500).all()
    else:
        records = []

    men, women = analyzer.raise_candidates(records)
    show_sorry = False if men or women else True
    return render_template(
                'search.html',
                query = query,
                men = men,
                women = women,
                show_sorry = show_sorry
            )


@app.route('/resultAPI', methods=['POST'])
def result_detail():
    body = request.get_json()
    id = body['id']
    result = db.session.query(
                Record,
                Meet,
                Swimmer,
                Team
            ).filter(
                Record.meet_id == Meet.meet_id,
                Record.swimmer_id == Swimmer.swimmer_id,
                Record.team_id == Team.team_id,
                Record.record_id == id
            ).first()

    rtn = analyzer.result_dictionary(result)
    time = result.Record.time
    year = result.Meet.year
    grade = getattr(result.Swimmer, f'grade_{year}')
    rtn['dev1'] = deviation(time, result.Meet.pool, result.Record.event, 0)
    rtn['dev2'] = deviation(time, result.Meet.pool, result.Record.event, grade)
    return jsonify(rtn)


def count_faster_swimmer(pool, event, year, grades, time_limit):
    # 自分より速いスイマーの数を数える
    conditions = set_conditions(pool, event, year, grades, time_limit)
    count = db.session.query(Swimmer.swimmer_id).distinct(Swimmer.swimmer_id).filter(*conditions).count()
    return count + 1

@app.route('/rankAPI', methods=['POST'])
def time_and_rank():
    body = request.get_json()
    index = body['index']
    time_val = body['time_val']
    event = body['event_code']
    pool = body['pool']
    grade = body['grade']
    year = CURRENT_YEAR

    if event: # 二種目目がない人は0が格納されている
        whole_stats = db.session.query(Stats.count_ranking).filter_by(pool=pool, event=event, grade=0).one()
        whole_count = whole_stats.count_ranking
        same_grade_stats = db.session.query(Stats.count_ranking).filter_by(pool=pool, event=event, grade=grade).one()
        same_count = same_grade_stats.count_ranking
    else:
        whole_count = '-'
        same_count = '-'

    if time_val:
        time_limit = time_val - 1 # このタイム以下の人が探される
        whole_ranking = count_faster_swimmer(pool, event, year, None, time_limit)
        same_ranking = count_faster_swimmer(pool, event, year, [grade], time_limit)
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



@app.route('/up')
def wake_up(): # 監視サービスで監視する用のURL
    return 'ok'

@app.route(ADMIN_URL + '/count')
def count_and_store():
    race, swimmer, meet = count_row()
    r.set('count_race', race)
    r.set('count_swimmer', swimmer)
    r.set('count_meet', meet)
    return f'{race=} {swimmer=} {meet=}'

def get_rows_count():
    race = r.get('count_race')
    swimmer = r.get('count_swimmer')
    meet = r.get('count_meet')
    try:
        return int(race), int(swimmer), int(meet)
    except ValueError:
        return 0, 0, 0

def count_row():
    count_race = db.session.query(func.count(Record.record_id)).scalar()

    count_swimmer = db.session.query(
            func.count(Swimmer.swimmer_id)
        ).filter(
            # カンマを含むのはリレー
            ~Swimmer.name.contains(',')
        ).scalar()

    count_meet = db.session.query(
            Record.record_id
        ).distinct(
            Record.meet_id
        ).count()
    return count_race, count_swimmer, count_meet

if __name__ == "__main__": #gunicornで動かす場合は実行されない
    print('組み込みサーバーで起動します')
    app.run()
