# 循環importなんてするくらいならひとつのモジュールに統合させたほうがPythonらしいと思うんだ
import datetime
import os
import threading

from flask import Flask, request, render_template
from flask_sqlalchemy import SQLAlchemy

if os.name == 'nt': # ローカルのWindows環境なら、環境変数をその都度設定
    import env

import analyzer
from constant import style_2_num, distance_2_num, area_list, style_2_japanese, foreign_teams, event_2_num
import scraper
from task_manager import Takenoko, free, busy, get_status, notify_line

app = Flask(__name__)
app.config.from_object('config.Develop' if os.name == 'nt' else 'config.Product')
db = SQLAlchemy(app)
manegement_url = os.environ['ADMIN_URL']


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

    def __init__(self, meet_id):
        self.meetid = meet_id
        self.area = int(meet_id[:2])
        self.year = int(meet_id[2:4])
        self.code = int(meet_id[-2:])   # 下三桁
        self.start, self.end, self.name, self.place, self.pool = scraper.meet_info(meet_id)



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

    def __init__(self, meet_id, sex, style, distance, rank, name, team, grade, time, laps):
        self.meetid = meet_id
        self.sex = sex
        self.style = style
        self.distance = distance
        _, self.name, self.team, self.grade, self.time, self.laps = (
            rank, name, team, grade, time, laps)

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

    def __init__(self, meet_id, sex, style, distance, rank, name, team, grade, time, laps):
        self.meetid = meet_id
        self.sex = sex
        self.style = style
        self.distance = distance
        self.rank, names, self.team, _, self.time, self.laps = (
            rank, name, team, grade, time, laps)
        self.name_1, self.name_2, self.name_3, self.name_4 = names


class Statistics(db.Model): #種目の平均値、標準偏差
    __tablename__ = 'statistics'
    id = db.Column(db.Integer, primary_key=True)                      # 連番で振られるid
    pool = db.Column(db.Integer, nullable = False)                    # 0 (短水路) or 1(長水路)
    sex = db.Column(db.Integer, nullable = False)                     # 性別
    style = db.Column(db.Integer, nullable = False)                   # 泳法
    distance = db.Column(db.Integer, nullable = False)                # 距離
    agegroup = db.Column(db.String, nullable = False)                 # 全体・小学・中学・高校・大学・一般
    average = db.Column(db.Float)                                     # タイムの平均値 100倍秒数値
    std = db.Column(db.Float)                                          # 標準偏差    100倍秒数値
    max500th = db.Column(db.String)                                   # 500番目のタイム。#:##.##書式文字列
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
    print('全432種目の記録分布の分析を開始')
    stats = db.session.query(Statistics).all()
    for st in Takenoko(stats, 20):
        records = (db.session.query(Record, Meet)
            .filter(Record.sex==st.sex, Record.style==st.style, Record.distance==st.distance, Record.time != "", Record.meetid == Meet.meetid, Meet.pool == st.pool)
            .all())
        st.average, st.std, st.max500th, st.count = analyzer.compile_statistics(records, st.agegroup)
        del records
        db.session.commit()
    print('全種目の分析を完了')
    free()

def calc_deviation(value, average, std):
    res = (value - average) / std * -10 + 50 #数値が少ないほうが高くしたいので－10かけ
    return round(res, 1)


def add_records(target_meets_ids): # 大会IDのリストから１大会ごとにRecordかRelayの行を生成しDBに追加
    notify_line(f">>> {len(target_meets_ids)}の大会の全記録の抽出開始")
    count_records = 0
    for meet_id in Takenoko(target_meets_ids, 20):
        for event in scraper.all_events(meet_id):
            set_args_4_records = event.all_records()
            if event.is_indivisual:
                records = [Record(*args) for args in set_args_4_records]
            else:
                records = [Relay(*args) for args in set_args_4_records]
            count_records += len(records)
            db.session.add_all(records)
            db.session.commit()

    total = '{:,}'.format(count_query())
    notify_line(f'>>> 全{count_records}件の記録の保存完了 現在：{total}件')
    free()

def add_meets(year):
    print(f">>> 20{year}年開催の大会IDの収集を開始")
    meet_ids = []
    for area in Takenoko(area_list):
        meet_ids.extend(scraper.find_meet(year, area))
    print(f'>>> 20{year}年に開催される全{len(meet_ids)}の大会情報を取得中')
    meets = [Meet(id) for id in Takenoko(meet_ids, 20)]
    db.session.add_all(meets)
    db.session.commit()
    print(f'>>> 全{len(meets)}の大会情報の保存が完了')
    free()

def count_query():
    count = db.session.query(Record).count()
    count += db.session.query(Relay).count()
    return count

####### 以下ルーター #######
@app.route('/')
def index():
    return render_template('index.html', count_records=count_query())

@app.route('/up')
def wake_up(): # 監視サービスで監視する用のURL
    return 'ok'


@app.route('/dashboard')
def dashboard():
    id = request.args.get('id', 1, type=int)
    target = db.session.query(Record).get(id)
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
    swimmer = analyzer.Swimmer(records)
    swimmer.sex = 'men' if sex == 1 else 'women'
    swimmer.name = name
    swimmer.grade = grade
    swimmer.teams = teams

    # S1偏差値の導出
    s1_event = swimmer.s1['event_name']
    if s1_event == '':
        swimmer.dev_long, swimmer.dev_short = '', ''
    else:
        s1_style = event_2_num[s1_event]['style'] # DB検索用に数字に戻す
        s1_distance = event_2_num[s1_event]['distance']
        stats = db.session.query(Statistics).filter_by(sex=sex, style=s1_style, distance=s1_distance, agegroup=grade[:2]).order_by(Statistics.pool).all() # 1番目が短水路、2番目が長水路になる
        swimmer.dev_short = calc_deviation(swimmer.s1['short_best'], stats[0].average, stats[0].std) if swimmer.s1['short_best'] is not None else '-'
        swimmer.dev_long = calc_deviation(swimmer.s1['long_best'], stats[1].average, stats[1].std) if swimmer.s1['long_best'] is not None else '-'

    return render_template('dashboard.html', s = swimmer)


@app.route('/ranking',  methods = ['POST', 'GET'])
def ranking():
    pool = request.args.get('pool', 1, type=int)
    sex = request.args.get('sex', 1, type=int)
    style = request.args.get('style', 'Fr')
    distance = request.args.get('distance', 50, type=int)
    page = request.args.get('page', 1, type=int)
    grades = request.form.getlist("grade") # POST時のフォームの内容が格納される GET時は空リスト
    ranking_length = 0

    if grades:
        records = (db.session.query(Record, Meet)
                .filter(Record.sex==sex, Record.style==style_2_num[style], Record.distance==distance_2_num[distance], Record.grade.in_(grades), Record.time != "", Record.meetid == Meet.meetid, Meet.pool == pool)
                .all())
    elif page == 1:
        target_event = db.session.query(Statistics).filter_by(pool=pool, sex=sex, style=style_2_num[style], distance=distance_2_num[distance], agegroup='全体').first()
        time_limit = target_event.max500th
        records = (db.session.query(Record, Meet)
                .filter(Record.sex==sex, Record.style==style_2_num[style], Record.distance==distance_2_num[distance], Record.time != "", Record.time <= time_limit, Record.meetid == Meet.meetid, Meet.pool == pool)
                .all()) # sortはORM側でやるのが早いのかそれともpandasに渡してからやったほうが早いのか…
        ranking_length = target_event.count
    else:
        records = (db.session.query(Record, Meet)
                .filter(Record.sex==sex, Record.style==style_2_num[style], Record.distance==distance_2_num[distance], Record.time != "", Record.meetid == Meet.meetid, Meet.pool == pool)
                .all()) # sortはORM側でやるのが早いのかそれともpandasに渡してからやったほうが早いのか…

    df_ = analyzer.output_ranking(records)
    if ranking_length == 0:
        ranking_length = len(df_)
    print(f'query: all:{len(records)} rank:{ranking_length} sex:{sex} pool:{pool} style:{style} distance:{distance}')
    data_from = 500*(page-1)
    data_till = 500*page
    df = df_[data_from:data_till] # 1ページ目なら[0:500]
    # {% for rank, id, name, time, grade, team in ranking %}
    ranking = zip(range(data_from+1, data_till+1), df['id'], df['name'], df['time'], df['grade'], df['team'])

    max_page = (ranking_length - 1) // 500 + 1
    group = f'pool={pool}&sex={sex}'
    group_bools = [' selected' if pool==0 and sex==1 else '',
                ' selected' if pool==1 and sex==1 else '',
                ' selected' if pool==0 and sex==2 else '',
                ' selected' if pool==1 and sex==2 else '']
    current_event = f'style={style}&distance={distance}'
    str_sex = 'men' if sex == 1 else 'women'
    jpn_group = f'{"男子" if sex == 1 else "女子"} {"長水路" if pool == 1 else "短水路"}'
    jpn_event = f'{distance}m {style_2_japanese[style]}'

    return render_template(
            'ranking.html',
            ranking = ranking,
            group = group,
            group_bools = group_bools,
            current_event = current_event,
            jpn_group = jpn_group,
            jpn_event = jpn_event,
            str_sex = str_sex,
            grades = grades,
            current_page = page,
            max_page = max_page)


@app.route('/search', methods=['GET','POST'])
def search():
    if request.method == 'POST':
        name = request.form.get('name', '').replace(' ','').replace('_','').replace('%','')
        team = request.form.get('team', '').replace(' ','').replace('_','').replace('%','')
        exact = True if request.form.get('exact', '') == 'true' else False
    else:
        name = request.args.get('name')
        team = request.args.get('team')
        exact = True

    if name and exact:
        records = db.session.query(Record).filter(Record.name == name).all()
        msg = f'選手: "{name}" の検索結果 (完全一致)'
    elif name and not exact:
        records = db.session.query(Record).filter(Record.name.like(f"%{name}%")).all()
        msg = f'選手: "{name}" の検索結果 (部分一致)'
    elif team and exact:
        team_mates = db.session.query(Record).filter(Record.team == team).all()
        msg = f'団体: "{team}" の検索結果 (完全一致)'
    elif team and not exact:
        team_mates = db.session.query(Record).filter(Record.team.like(f"%{team}%")).all()
        msg = f'団体: "{team}" の検索結果 (部分一致)'
    else:
        records = []
        msg = ''

    # team_matesは検索したチームから出た記録しか抽出されないので、各選手の他のチームから出た記録も検索
    if team:
        names = {m.name for m in team_mates}
        records = db.session.query(Record).filter(Record.name.in_(names)).all()

    candidates = analyzer.raise_candidates(records)
    show_sorry = False if candidates else True
    return render_template(
            'search.html',
            message = msg,
            candidates = candidates,
            show_sorry = show_sorry)


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
        # リストでフィルターをかけているが、deleteの引数synchronize_sessionのデフォルト値'evaluate'ではこれをサポートしていない(らしい)からFalseを指定する
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
