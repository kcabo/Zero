# 循環importなんてするくらいならひとつのモジュールに統合させたほうがPythonらしいと思うんだ
import datetime
import os
import threading

from flask import Flask, request, render_template
from flask_sqlalchemy import SQLAlchemy

if os.name == 'nt': # ローカルのWindows環境なら、環境変数をその都度設定
    import env

import analyzer
from constant import style_2_num, distance_2_num, area_list, style_2_japanese, style_and_distance, japanese_grades
import scraper
from task_manager import Takenoko, status, notify_line

app = Flask(__name__)
app.config.from_object('config.Develop' if os.name == 'nt' else 'config.Product')
db = SQLAlchemy(app)
manegement_url = os.environ['ADMIN_URL'] # 秘密の管理用のURLを環境変数から取得


class Meet(db.Model):
    __tablename__ = 'meets'
    id = db.Column(db.Integer, primary_key=True)                      # 自動で連番で振られるid
    meetid = db.Column(db.Integer, unique = True, nullable = False)   # 7桁の大会ID 0119721など0で始まる場合は6桁になる
    name = db.Column(db.String, nullable = False)                     # 大会名
    place = db.Column(db.String, nullable = False)                    # 会場
    pool = db.Column(db.Integer, nullable = False)                    # 0 (短水路) or 1(長水路)
    start = db.Column(db.Integer, nullable = False)                   # 大会開始日 20190924 の整数型で表す
    end = db.Column(db.Integer, nullable = False)                     # 大会終了日
    area = db.Column(db.Integer, nullable = False)                    # 地域(整数2桁)
    year = db.Column(db.Integer, nullable = False)                    # 開催年(2桁)
    code = db.Column(db.Integer, nullable = False)                    # 下三桁

    def __str__(self):
        return str((self.id, self.meetid, self.name, self.pool, self.start))

    def __init__(self, meet_id): # 渡されるのは整数
        self.meetid = meet_id    # 十万から900万くらいまで
        self.area = meet_id // 100000
        tmp = meet_id % 100000   # エリアコード省いた値。19721とかになる
        self.year = tmp // 1000
        self.code = tmp % 1000   # 下三桁
        self.start, self.end, self.name, self.place, self.pool = scraper.meet_info(meet_id)


class Record(db.Model): # 個人種目とリレーの記録
    __tablename__ = 'records'
    id = db.Column(db.Integer, primary_key=True)                      # 自動で連番で振られるid
    meetid = db.Column(db.Integer, nullable = False)                  # 7桁の大会ID 0119721など0で始まる場合は6桁になる
    event = db.Column(db.Integer, nullable = False)                   # 性別・スタイル・距離をつなげた整数
    relay = db.Column(db.Integer, nullable = False)                   # 個人種目なら0、リレー一泳なら1,以後2,3,4泳。リレー全体記録なら5。
    rank = db.Column(db.String, nullable = False)                     # 順位や棄権、失格情報など
    name = db.Column(db.String, nullable = False)                     # 選手氏名。リレーのときはカンマでつなげて4人
    team = db.Column(db.String, nullable = False)                     # 所属名
    grade = db.Column(db.Integer, nullable = False)                   # 学年 小学1年生 1 から 一般19まで リレー記録は0 無効な学年は-1
    time = db.Column(db.Integer, nullable = False)                    # タイム。百倍秒数(hecto_seconds)。失格棄権は0。意味不明タイムは-1
    laps = db.Column(db.String, nullable = False)                     # ラップタイム。百倍秒数をカンマでつなげる

    def __init__(self, meet_id, event, relay, rank, name, team, grade, time, laps):
        self.meetid, self.event, self.relay, self.rank, self.name, self.team, self.grade, self.time, self.laps = (
            meet_id, event, relay, rank, name, team, grade, time, laps)


class Stats(db.Model): #種目の平均値、標準偏差
    __tablename__ = 'stats'
    id = db.Column(db.Integer, primary_key=True)                      # 自動で連番で振られるid
    pool = db.Column(db.Integer, nullable = False)                    # 0 (短水路) or 1(長水路)
    event = db.Column(db.Integer, nullable = False)                   # 性別・スタイル・距離をつなげた整数 25mも含める 混合は含めない
    agegroup = db.Column(db.Integer, nullable = False)                # 0全体・1小学・2中学・3高校・4大学・5一般
    mean = db.Column(db.Float)                                        # タイムの平均値 100倍秒数値
    std = db.Column(db.Float)                                         # 標準偏差
    q1 = db.Column(db.Integer)                                        # 第一四分位 百倍秒数。小さい、つまり速い方
    q2 = db.Column(db.Integer)                                        # 第二四分位。中央値 百倍秒数
    q3 = db.Column(db.Integer)                                        # 第三四分位 百倍秒数
    border = db.Column(db.Integer)                                    # 500番目のタイム。百倍秒数
    count = db.Column(db.Integer)                                     # その種目のランキング化したあとの人数 外れ値含む

    def __init__(self, pool, event, agegroup):
        self.pool, self.event, self.agegroup = pool, event, agegroup


def initialize_stats_table():
    for pool in [0, 1]:
        for sex in [1, 2]:
            for sd in style_and_distance:
                for agegroup in [0, 1, 2, 3, 4, 5]:
                    event = sex * 100 + sd
                    row = Stats(pool, event, agegroup)
                    db.session.add(row)
    db.session.commit()


def analyze_all():
    # statisticsテーブルの行を一行ずつ見ていき、それぞれアップデート
    notify_line('全696種目の記録分布の分析を開始')
    stats = db.session.query(Stats).all()
    for st in Takenoko(stats, 20):
        records = (db.session.query(Record, Meet)
            .filter(Record.event==st.event, Record.time > 0, Record.meetid == Meet.meetid, Meet.pool == st.pool).all())
        st.mean, st.std, st.q1, st.q2, st.q3, st.border, st.count = analyzer.compile_statistics(records, st.agegroup)
        del records
        db.session.commit()
    notify_line('全種目の分析を完了')
    status.free()

def calc_deviation(value, mean, std):
    answer = (value - mean) / std * -10 + 50 #数値が少ないほうが高くしたいので－10かけ
    return round(answer, 1)


def add_records(target_meets_ids): # 大会IDのリストから１大会ごとにRecordの行を生成しDBに追加
    notify_line(f">>> {len(target_meets_ids)}の大会の全記録の抽出開始")
    count_records = 0
    for meet_id in Takenoko(target_meets_ids, 20):
        records = []
        for event in scraper.all_events(meet_id):
            records.extend([Record(*args) for args in event.crawl_table()])

        # ひとつの大会が終わるごとにもともとあったレコードを削除して、新たにゲットしたのを追加
        db.session.query(Record).filter_by(meetid=meet_id).delete()
        db.session.add_all(records)
        count_records += len(records)
        del records
        db.session.commit()

    notify_line(f'>>> 全{count_records}件の記録の保存完了 現在：{format(total_count(), ",")}件')
    status.free()

def add_meets(year):
    print(f">>> 20{year}年開催の大会IDの収集を開始")
    meet_ids = [] # 整数型を入れる
    for area in Takenoko(area_list): # area_listには01などの文字列が格納
        meet_ids.extend(scraper.find_meet(year, area))
    print(f'>>> 20{year}年に開催される全{len(meet_ids)}の大会情報を取得中')
    meets = [Meet(id) for id in Takenoko(meet_ids, 20)]
    db.session.query(Meet).filter_by(year = year).delete() # 同じ年度を二重に登録しないように削除する
    db.session.add_all(meets)
    db.session.commit()
    print(f'>>> 全{len(meets)}の大会情報の保存が完了')
    status.free()

def total_count():
    count = db.session.query(Record).count()
    return count


####### 以下ルーター #######
@app.route('/')
def index():
    return render_template('index.html', count_records=total_count())

@app.route('/up')
def wake_up(): # 監視サービスで監視する用のURL
    return 'ok'


@app.route('/dashboard')
def dashboard():
    # GETでパラメータにRecordsのIDを格納しているので誰の記録か探す
    id = request.args.get('id', 1, type=int)
    target = db.session.query(Record).get(id)

    # 検索のために選手の情報を取得
    sex = target.event // 100 # event百の位が性別
    name = target.name
    grade = target.grade # 整数

    # 取得した選手の名前・学年でフィルタリングしてrecordsテーブルから取得
    # 同時にそれぞれのrecordのmeetidからMeetを内部結合
    records = (db.session.query(Record, Meet)
            .filter(Record.name == name, Record.grade == grade, Record.meetid == Meet.meetid)
            .all())

    # 見出しの選手情報：     性別　名前　学年　所属一覧
    teams = {r.Record.team for r in records} # set型なので重複削除される
    swimmer = analyzer.Swimmer(records)
    del records # メモリ削減。効果ないかも
    swimmer.sex = 'men' if sex == 1 else 'women'
    swimmer.name = name
    swimmer.grade = japanese_grades[grade]
    swimmer.teams = teams

    # S1偏差値の導出
    s1_event = swimmer.s1['event_name']
    if s1_event == '':
        swimmer.dev_long, swimmer.dev_short = '', ''
    else:
        target_event_num = swimmer.s1['event_number']
        # 0全体・1小学・2中学・3高校・4大学・5一般
        agegroup_list = [0,1,1,1,1,1,1,2,2,2,3,3,3,4,4,4,4,4,4,5]
        agegroup = agegroup_list[grade] # gradeからagegroupへの変換 gradeは1以上なので最初の0が選ばれることはない
        stats = db.session.query(Stats).filter_by(event=int(target_event_num), agegroup=agegroup).order_by(Stats.pool).all() # 1番目が短水路、2番目が長水路になる
        swimmer.dev_short = calc_deviation(swimmer.s1['short_best'], stats[0].mean, stats[0].std) if swimmer.s1['short_best'] is not None else '-'
        swimmer.dev_long = calc_deviation(swimmer.s1['long_best'], stats[1].mean, stats[1].std) if swimmer.s1['long_best'] is not None else '-'

    return render_template('dashboard.html', s = swimmer)


@app.route('/ranking',  methods = ['POST', 'GET'])
def ranking():
    pool = request.args.get('pool', 1, type=int)
    sex = request.args.get('sex', 1, type=int)
    style = request.args.get('style', 'Fr')
    distance = request.args.get('distance', 50, type=int)
    page = request.args.get('page', 1, type=int)
    grades = request.form.getlist("grade", type=int) # POST時のフォームの内容が格納されるGET時は空リスト
    event = sex * 100 + style_2_num[style] * 10 + distance_2_num[distance]
    ranking_length = 0

    if grades:
        records = (db.session.query(Record, Meet)
                .filter(Record.event==event, Record.grade.in_(grades), Record.time > 0, Record.meetid == Meet.meetid, Meet.pool == pool)
                .all())
    elif page == 1:
        target_event = db.session.query(Stats).filter_by(pool=pool, event=event, agegroup=0).one()
        time_limit = target_event.border
        records = (db.session.query(Record, Meet)
                .filter(Record.event==event, Record.time > 0, Record.time <= time_limit, Record.meetid == Meet.meetid, Meet.pool == pool)
                .all())
        ranking_length = target_event.count
    else:
        records = (db.session.query(Record, Meet)
                .filter(Record.event==event, Record.time > 0, Record.meetid == Meet.meetid, Meet.pool == pool)
                .all())

    df_ = analyzer.output_ranking(records)
    if ranking_length == 0:
        ranking_length = len(df_)
    data_from = 500*(page-1)
    data_till = 500*page
    df = analyzer.format_grade_and_time(df_[data_from:data_till]) # 1ページ目なら[0:500] 学年とタイムを文字列変換
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
        records = db.session.query(Record).filter(Record.name == name, Record.relay == 0).all()
        msg = f'選手: "{name}" の検索結果 (完全一致)'
        placeholder = name
    elif name and not exact:
        records = db.session.query(Record).filter(Record.name.like(f"%{name}%"), Record.relay == 0).all()
        msg = f'選手: "{name}" の検索結果 (部分一致)'
        placeholder = name
    elif team and exact:
        team_mates = db.session.query(Record).filter(Record.team == team, Record.relay == 0).all()
        msg = f'所属: "{team}" の検索結果 (完全一致)'
        placeholder = team
    elif team and not exact:
        team_mates = db.session.query(Record).filter(Record.team.like(f"%{team}%"), Record.relay == 0).all()
        msg = f'所属: "{team}" の検索結果 (部分一致)'
        placeholder = team
    else:
        records = []
        msg = ''
        placeholder = 'Search...'

    # team_matesは検索したチームから出た記録しか抽出されないので、各選手の他のチームから出た記録も検索
    if team:
        names = {m.name for m in team_mates}
        records = db.session.query(Record).filter(Record.name.in_(names), Record.relay == 0).all()

    candidates = analyzer.raise_candidates(records)
    show_sorry = False if candidates else True
    return render_template(
            'search.html',
            message = msg,
            placeholder = placeholder,
            candidates = candidates,
            show_sorry = show_sorry)


def check_is_busy():
    s = status.get_status()
    is_busy = True if s == 'busy' else False
    return is_busy

def all_threads():
    thread_list = [t.name for t in threading.enumerate()] # 起動中のスレッド一覧を取得
    threads = ' / '.join(thread_list)
    return threads

@app.route(manegement_url)
def admin_no_offer():
    return render_template(
        'admin.html',
        is_busy = check_is_busy(),
        threads = all_threads(),
        admin_url = manegement_url
    )

@app.route(manegement_url + '/<command>')
def admin_without_threads(command):
    msg = ''
    obj = ''
    if command == 'create':
        db.create_all()
        obj = 'create_all'

    elif command == 'drop':
        db.drop_all()
        obj = 'drop_all'

    elif command == 'foreign':
        from constant import foreign_teams
        count = db.session.query(Record).filter(Record.team.in_(foreign_teams)).count()
        # リストでフィルターをかけているが、deleteの引数synchronize_sessionのデフォルト値'evaluate'ではこれをサポートしていない(らしい)からFalseを指定する
        db.session.query(Record).filter(Record.team.in_(foreign_teams)).delete(synchronize_session = False)
        db.session.commit()
        msg = f'total: {count}'
        obj = 'erase_foreign'

    elif command == 'init_stats':
        db.session.query(Stats).delete()
        initialize_stats_table()
        obj = 'init_stats'

    return render_template(
        'admin.html',
        show_pane = True,
        is_done = True,
        obj = obj,
        is_busy = check_is_busy(),
        threads = all_threads(),
        admin_url = manegement_url
    )

@app.route(manegement_url + '/thread/<command>')
def admin_with_threads(command): # 並列処理実行
    is_busy = check_is_busy()
    show_pane = False
    show_rejected = True
    invalid_url = True
    obj = ''
    msg = ''

    if is_busy:
        invalid_url = False

    elif command in ['meets', 'records', 'stats']:
        range = request.args.get('range', default=None, type=int)
        date_min = request.args.get('from', default="20190401")
        date_max = request.args.get('to', default="20190404")
        year = request.args.get('year', default=19, type=int)

        show_pane = True
        show_rejected = False
        if command == 'meets':
            th = threading.Thread(target=add_meets, name='scraper_y', args=(year,))
            obj = 'add_meets'
            msg = f'year: {year}'

        elif command == 'records':
            if range:
                today = datetime.date.today()
                week_ago = today - datetime.timedelta(days=range)
                date_min = week_ago.strftime('%Y%m%d')
                date_max = today.strftime('%Y%m%d')
            target_meets = db.session.query(Meet).filter(Meet.start >= int(date_min), Meet.start <= int(date_max)).order_by(Meet.start).all()
            target_meets_ids = [m.meetid for m in target_meets]
            th = threading.Thread(target=add_records, name='scraper_r', args=(target_meets_ids,))
            obj = 'add_records'
            msg = f'from: {date_min}  to: {date_max}'

        elif command == 'stats':
            th = threading.Thread(target=analyze_all, name='stats')
            obj = 'analyze_all'

        status.busy()
        db.session.commit()
        th.start()
    return render_template(
        'admin.html',
        show_pane = show_pane,
        is_done = False,
        obj = obj,
        msg = msg,
        show_rejected = show_rejected,
        invalid_url = invalid_url,
        is_busy = True,
        threads = all_threads(),
        admin_url = manegement_url
    )


if __name__ == "__main__": #gunicornで動かす場合は実行されない
    print('組み込みサーバーで起動します')
    app.run()
