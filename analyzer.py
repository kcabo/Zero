import datetime
import pandas as pd
from constant import japanese_grades, FormatEvent

def val_2_fmt(val):
    if val > 0:
        min = val // 6000
        hecto_seconds = val % 6000
        sec = hecto_seconds // 100
        centi_sec = hecto_seconds % 100
        return f'{min}:{format(sec,"02")}.{format(centi_sec,"02")}'
    else:
        return ''

class Point: # 折れ線グラフの1座標
    def __init__(self, x, y):
        self.x = x
        self.y = y
    def __repr__(self):
        return f'{{x:{self.x},y:{self.y}}}'

def count_style(styles): # ['Fr', 'Ba', 'Br', 'Fly', 'IM'] の順で出現頻度のリストを生成
    dic = styles.value_counts(normalize=True).to_dict()
    return [int(dic.get(s, 0) * 100) for s in [1,2,3,4,5]]

def trend_points(df):
    if len(df) == 0:
        return [] # 記録なし
    else:
        max = df['time_val'].max()
        min = df['time_val'].min()
        if max == min: # 最大と最小が等しいときはy値は50で固定(ゼロ除算が発生し標準化できないから)
            return [Point(days, 50) for days in df['days']]
        else:
            normalized = df['time_val'].map(lambda x:((max - x)*100)/(max - min)) # ワーストを0,ベストを100として標準化
            return [Point(days, int(n)) for days, n in zip(df['days'], normalized)]

class BestsCard:
    def __init__(self, df, targets): # targetsはevent_valの下二桁を格納したリスト
        df['event_val'] = df['event_val'] % 100
        df = df[df['event_val'].isin(targets)].copy() # 下二桁が一致するやつだけ抜き出す
        if len(df) == 0:
            self.events = False
        else:
            self.events = [FormatEvent(100 + t) for t in targets]
            results = [BestResult() for i in range(6)] # placeholder
            df['order'] = df['event_val'].map(lambda x: targets.index(x)) # リストの何番目か 0~2
            for order, pool, id, time, start in zip(df['order'], df['pool'], df['id'], df['time'], df['start']):
                i = order * 2 + pool  # ここ天才
                results[i].id = id
                results[i].time = time
                results[i].date = start
            self.results = results

class BestResult:
    def __init__(self): # 初期値に空白文字を設定
        self.id = ''
        self.time = ''
        self.date = ''

class Swimmer:
    def __init__(self, records):
        converted = map(lambda x:(x.Record.id, x.Record.event, x.Record.time, x.Meet.pool, x.Meet.start, x.Meet.name), records)
        df = pd.DataFrame(converted, columns = ['id', 'event_val', 'time_val', 'pool', 'start', 'meet_name'])
        df['event'] = df['event_val'].map(lambda x: FormatEvent(x))
        df['time'] = df['time_val'].map(val_2_fmt) # 読める形にフォーマット
        df['start'] = df['start'].map(lambda x: datetime.datetime.strptime(str(x), '%Y%m%d').strftime('%Y/%m/%d')) # 日付を文字列型でフォーマット

        df2 = df.sort_values(['start', 'event_val', 'time_val'], ascending=[False, True, True]) # 日付のみ新しい順に
        self.records = zip(df2['id'], df2['event'], df2['time'], df2['pool'], df2['start'], df2['meet_name'])
        df = df[df['time_val'] > 0] # 空白タイム削除

        self.total_count = len(df)
        self.count_race = count_style(df['event'].map(lambda x: x.style))

        # 折れ線グラフ化する最多出場の2種目を選ぶ
        event_counts = df['event_val'].value_counts()
        e1 = event_counts.index[0] if len(event_counts) > 0 else 0  # 出場種目が棄権しか無いと得意種目すら無い
        e2 = event_counts.index[1] if len(event_counts) > 1 else 0 # 1種目しか出場しておらずS2が無いときは空白

        from_date = datetime.datetime(2019,4,1) # 経過日数の基準となる日付
        df['days'] = df['start'].map(lambda x: (datetime.datetime.strptime(x, '%Y/%m/%d') - from_date).days) # 日付のシリアル化 基準日からの経過日数
        df.sort_values(['pool', 'event_val', 'days', 'time_val'], inplace=True) # すべて昇順で並び替え
        df.drop_duplicates(subset=['pool', 'event_val', 'days'], inplace=True) # 同じ日の同じレース（予選と決勝など）は早い方のタイムを残す

        self.trends = [] # e1 の短長、e2の短長で4つ順番に入る
        self.trends.append(trend_points(df[(df['event_val'] == e1) & (df['pool'] == 0)]))
        self.trends.append(trend_points(df[(df['event_val'] == e1) & (df['pool'] == 1)]))
        self.trends.append(trend_points(df[(df['event_val'] == e2) & (df['pool'] == 0)]))
        self.trends.append(trend_points(df[(df['event_val'] == e2) & (df['pool'] == 1)]))

        df.sort_values(['time_val', 'pool'], inplace=True) # タイム順速いに並び替え
        df.drop_duplicates(['pool', 'event_val'], inplace=True) # 種目、水路をユニークにする。一番速いタイムのみ残る。これで残っている記録はすべてベストになる

        # 偏差値導出のためのベストをvalueでぬきだす ない場合は空リスト 有るときはリストの1個目 int関数はnumpy64をpython型に変換してる
        self.events = [FormatEvent(e) for e in [int(e1), int(e2)]]
        self.e1bests = (df['time_val'][(df['event_val'] == e1) & (df['pool'] == 0)].tolist(),
                    df['time_val'][(df['event_val'] == e1) & (df['pool'] == 1)].tolist())
        self.e2bests = (df['time_val'][(df['event_val'] == e2) & (df['pool'] == 0)].tolist(),
                    df['time_val'][(df['event_val'] == e2) & (df['pool'] == 1)].tolist())

        # 6カテゴリ(5種目＋長距離)のベストをカードごとのインスタンスとして作成
        cards = []
        cards.append(BestsCard(df, [12, 13, 14]))
        cards.append(BestsCard(df, [15, 16, 17]))
        cards.append(BestsCard(df, [22, 23, 24]))
        cards.append(BestsCard(df, [32, 33, 34]))
        cards.append(BestsCard(df, [42, 43, 44]))
        cards.append(BestsCard(df, [53, 54, 55]))
        self.cards = [card for card in cards if card.events] # ベストのないカードはeventsアトリビュートがFalse


class Candidate:
    def __init__(self, df):
        self.id = df.iloc[0]['id']
        self.sex = 'men' if df.iloc[0]['sex'] == 1 else 'women'
        self.name = df.iloc[0]['name']
        grade = df.iloc[0]['grade']
        self.grade = grade
        self.grade_jp = japanese_grades[grade]
        teams = df['team'].unique()
        self.teams = teams.tolist()

def raise_candidates(records):
    fixed = map(lambda x:(x.id, x.event, x.name, x.team, x.grade), records)
    df = pd.DataFrame(fixed, columns = ['id', 'event', 'name', 'team', 'grade'])
    df['sex'] = df['event'] // 100
    unique = df.drop_duplicates(subset=['sex', 'name', 'grade']).copy()
    unique.sort_values(['sex', 'name'], inplace=True)

    candidates = []
    for sex, name, grade in zip(unique['sex'], unique['name'], unique['grade']):
        c = Candidate(df[(df['sex'] == sex) & (df['name'] == name) & (df['grade'] == grade)])
        candidates.append(c)

    return candidates

def format_ranking(df):
    df['time'] = df['time_val'].map(val_2_fmt)
    df['grade_jp'] = df['grade'].map(lambda x: japanese_grades[x])
    week_ago = datetime.date.today() - datetime.timedelta(days=7)
    week_ago_int = int(week_ago.strftime('%Y%m%d'))
    df['new'] = df['start'] >= week_ago_int
    return df

def output_ranking(records):
    fixed = map(lambda x:(x.Record.id, x.Record.name, x.Record.team, x.Record.grade, x.Record.time, x.Meet.start), records)
    df = pd.DataFrame(fixed, columns = ['id', 'name', 'team', 'grade', 'time_val', 'start'])
    df.sort_values(['time_val'], inplace=True)
    df.drop_duplicates(subset=['name','grade'], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def compile_statistics(records, agegroup):
    # agegroup ... 0全体・1小学・2中学・3高校・4大学・5一般
    grades_list = [[], [1,2,3,4,5,6], [7,8,9], [10,11,12], [13,14,15,16,17,18], [19]]
    df = output_ranking(records)
    if agegroup == 0:
        vals = df['time_val']
        border = int(df.at[499, 'time_val']) if len(df) >= 500 else 999999 # 500人もランキングがいなかったなら99万をセット
    else:
        target_grades = grades_list[agegroup] # 対象の学年のリストを取り出す
        vals = df[df['grade'].isin(target_grades)]['time_val']
        border = 0
    count = len(vals)
    if count < 2: # データ少ないと統計値計算できない
        return None, None, None, None, None, None, count
    else:
        # 外れ値除くための範囲を決める
        q1 = vals.quantile(.25)
        q3 = vals.quantile(.75)
        iqr = q3-q1
        lower_limit = q1 - iqr * 1.5
        upper_limit = q3 + iqr * 1.5

        # 外れ値除外したやつの要約統計量を取得
        desc = vals[(vals > lower_limit) & (vals < upper_limit)].describe()
        mean = round(desc['mean'], 2) # 小数点第2位までで四捨五入
        std = round(desc['std'], 2)
        new_q1 = desc['25%']
        new_q2 = desc['50%']
        new_q3 = desc['75%']

        return mean, std, new_q1, new_q2, new_q3, border, count

def detail_dictionary(target):
    from constant import area_dict
    yobi = ["月","火","水","木","金","土","日"]
    start = datetime.datetime.strptime(str(target.Meet.start), '%Y%m%d')
    end = datetime.datetime.strptime(str(target.Meet.end), '%Y%m%d')
    my_event = FormatEvent(target.Record.event)
    res = {}
    res['start'] = start.strftime('%Y/%m/%d') + '(' + yobi[start.weekday()] + ')'
    res['end'] = '~' + end.strftime('%m/%d') + '(' + yobi[end.weekday()] + ')'
    res['area'] = area_dict[target.Meet.area]
    res['meet'] = target.Meet.name
    res['place'] = target.Meet.place
    res['pool'] = '長水路' if target.Meet.pool == 1 else '短水路'
    res['event'] = my_event.jpn_event()
    res['name'] = target.Record.name
    res['grade_jp'] = japanese_grades[target.Record.grade]
    res['team'] = target.Record.team
    res['time'] = val_2_fmt(target.Record.time)
    res['rank'] = target.Record.rank
    res['devrange'] = f'偏差値({res["grade_jp"][0:2]})' # 最初の二文字
    res['style'] = my_event.eng_style()
    res['grade'] = target.Record.grade

    laps_raw = target.Record.laps
    laps = [int(l) for l in laps_raw.split(',')]
    res['laps1'] = [val_2_fmt(l) for l in laps]
    res['laps2'] = [val_2_fmt(l) for l in calc_between_time(laps)]

    return res

def calc_between_time(laps): # ['0:32.83', '1:01.38','1:32.83', '2:11.38'];
    between = []
    for i in range(len(laps)):
        if i == 0:
            between.append(0)
        else:
            between.append(laps[i] - laps[i-1])
    return between
