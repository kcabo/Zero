import datetime
import pandas as pd
import os
import re

num_2_style = {
    1:"Fr",
    2:"Ba",
    3:"Br",
    4:"Fly",
    5:"IM",
    6:"FR",
    7:"MR"
}
num_2_distance = {
    1:25,
    2:50,
    3:100,
    4:200,
    5:400,
    6:800,
    7:1500
}

fmt_ptn = re.compile('([0-9]{1,2}):([0-9]{2}).([0-9]{2})') #15分とかのときは：の前は2文字になる
def fmt_2_val(fmt):
    match = re.match(fmt_ptn, fmt)
    min = int(match.group(1))
    sec = int(match.group(2)) * 100 + int(match.group(3))
    return min * 6000 + sec #100倍した秒数

class Swimmer:
    def __init__(self, records):
        converted = map(lambda x:(x.Record.id,
                            num_2_style[x.Record.style],
                            num_2_distance[x.Record.distance],
                            x.Record.time,
                            'l' if x.Meet.pool == 1 else 's',
                            x.Meet.start,
                            x.Meet.name), records)
        # 全レコード：id, スタイル　距離　記録　水路(l,m)　日付　大会名 のデータフレームを作成
        df = pd.DataFrame(converted, columns = ['id', 'style', 'distance', 'time', 'pool', 'start', 'meet_name'])
        df['event'] = df['distance'].astype(str) + df['style']          # 距離を文字列変換してから結合→50Frの形に

        self.records = df.sort_values(['start', 'style', 'distance', 'time'], ascending=[False, True, True, True]) # 日付のみ新しい順に
        df = df[df['time'] != ""] # 空白タイム削除

        self.total_count = len(df)
        self.count_style_long = self.count_style(df, "l") # 各種目に何回出場したか
        self.count_style_short = self.count_style(df, "s")

        # 折れ線グラフ化する最多出場の2種目を選ぶ ここでのS1はスタイルではなく距離も含めた種目
        event_counts = df['event'].value_counts()
        s1 = event_counts.index[0] if len(event_counts) > 0 else ''  # 出場種目が棄権しか無いと得意種目すら無い
        s2 = event_counts.index[1] if len(event_counts) > 1 else ''  # 1種目しか出場しておらずS2が無いときは空白
        self.s1 = {'event_name': s1}
        self.s2 = {'event_name': s2}

        from_date = datetime.datetime(2019,4,1) # 経過日数の基準となる日付
        df['days'] = df['start'].map(lambda x: (datetime.datetime.strptime(x, '%Y/%m/%d') - from_date).days) # 日付のシリアル化 基準日からの経過日数
        df['time_val'] = df['time'].map(fmt_2_val) # 100倍の秒数変換した列を生成
        df.sort_values(['pool', 'event', 'days', 'time_val'], inplace=True) # すべて昇順で並び替え
        df.drop_duplicates(subset=['pool', 'event', 'days'], inplace=True) # 同じ日の同じレース（予選と決勝など）は早い方のタイムを残す

        self.s1["long_trend"] = self.scatter_points(df[(df['event'] == s1) & (df['pool'] == 'l')])
        self.s1["short_trend"] = self.scatter_points(df[(df['event'] == s1) & (df['pool'] == 's')])
        self.s2["long_trend"] = self.scatter_points(df[(df['event'] == s2) & (df['pool'] == 'l')])
        self.s2["short_trend"] = self.scatter_points(df[(df['event'] == s2) & (df['pool'] == 's')])

        df.sort_values(['time_val'], inplace=True) # タイム順速いに並び替え
        df.drop_duplicates(['pool', 'event'], inplace=True) # 種目、水路をユニークにする。一番速いタイムのみ残る。これで残っている記録はすべてベストになる

        # 偏差値導出のためにS1のベストをvalueでぬきだす
        self.s1['long_best'] = self.first_val(df[(df['event'] == s1) & (df['pool'] == 'l')])
        self.s1['short_best'] = self.first_val(df[(df['event'] == s1) & (df['pool'] == 's')])

        # 6カテゴリ(5種目＋長距離)の辞書を作る。（ベストのないカテゴリはFalse)
        bests = {}
        bests['Fr_sprint'] = self.bests_dictionary(df[df['event'].isin(['50Fr','100Fr', '200Fr'])], ['50Fr','100Fr', '200Fr'])
        bests['Fr_endurance'] = self.bests_dictionary(df[df['event'].isin(['400Fr','800Fr', '1500Fr'])], ['400Fr','800Fr', '1500Fr'])
        bests['Ba'] = self.bests_dictionary(df[df['style'] == 'Ba'], ['50Ba','100Ba', '200Ba'])
        bests['Br'] = self.bests_dictionary(df[df['style'] == 'Br'], ['50Br','100Br', '200Br'])
        bests['Fly'] = self.bests_dictionary(df[df['style'] == 'Fly'], ['50Fly','100Fly', '200Fly'])
        bests['IM'] = self.bests_dictionary(df[df['style'] == 'IM'], ['100IM','200IM', '400IM'])
        self.bests = bests


    def count_style(self, df, pool): # ['Fr', 'Ba', 'Br', 'Fly', 'IM'] の順のリストを生成
        filtered = df[df['pool'] == pool]
        dic = filtered['style'].value_counts().to_dict()
        return [dic.get(s, 0) for s in ['Fr', 'Ba', 'Br', 'Fly', 'IM']]

    def scatter_points(self, df):
        if len(df) == 0:
            return '' # 記録なし
        else:
            max = df['time_val'].max()
            min = df['time_val'].min()
            if max == min: # 最大と最小が等しいときはy値は50で固定(ゼロ除算が発生し標準化できないから)
                points = [f"{{x:{days},y:50}}" for days in df['days']] # グラフのパラメータを文字列で作成
            else:
                normalized = df['time_val'].map(lambda x:((max - x)*100)/(max - min)) # ワーストを0,ベストを100として標準化
                points = [f"{{x:{days},y:{int(n)}}}" for days, n in zip(df['days'], normalized)] # グラフのパラメータを文字列で作成
            return ','.join(points)

    def first_val(self, df):
        return None if len(df) == 0 else df.iloc[0]['time_val']

    def bests_dictionary(self, df, keys):
        if len(df) == 0:
            return False
        else:
            dic = {}
            for key in keys:
                dic["l-" + key] = ['', '']
                dic["s-" + key] = ['', ''] # 初期値に空白文字を設定
            for event, time, start, pool in zip(df['event'], df['time'], df['start'], df['pool']):
                dic[pool + "-" + event] = [time, start] # 上書き
            return dic


class Candidate:
    def __init__(self, df):
        self.id = df.iloc[0]['id']
        self.sex = 'men' if df.iloc[0]['sex'] == 1 else 'women'
        self.name = df.iloc[0]['name']
        self.grade = df.iloc[0]['grade']
        teams = df['team'].unique()
        self.teams = teams.tolist()

def raise_candidates(records):
    fixed = map(lambda x:(x.id, x.sex, x.name, x.team, x.grade), records)
    df = pd.DataFrame(fixed, columns = ['id', 'sex', 'name', 'team', 'grade'])
    unique = df.drop_duplicates(subset=['sex', 'name', 'grade']).copy()
    unique.sort_values(['sex', 'name'], inplace=True)

    candidates = []
    for sex, name, grade in zip(unique['sex'], unique['name'], unique['grade']):
        c = Candidate(df[(df['sex'] == sex) & (df['name'] == name) & (df['grade'] == grade)])
        candidates.append(c)

    return candidates

def output_ranking(records):
    fixed = map(lambda x:(x.Record.id, x.Record.name, x.Record.team, x.Record.grade, x.Record.time), records)
    df = pd.DataFrame(fixed, columns = ['id', 'name', 'team', 'grade', 'time'])
    df['time_val'] = df['time'].map(fmt_2_val) # 記録を100倍の秒数に
    df.sort_values(['time_val'], inplace=True)
    df.drop_duplicates(subset=['name','grade'], inplace=True)
    # df = df.replace({'grade': {'学':' '}})
    df.reset_index(drop=True, inplace=True)
    return df

def compile_statistics(records, agegroup):
    df = output_ranking(records)
    if agegroup == '全体':
        vals = df['time_val']
        max500th = df.at[499, 'time'] if len(df) >= 500 else '99:99.00'
    else:
        vals = df[df['grade'].str.startswith(agegroup)]['time_val'] # 大学、などで学年が始まる行のみ取り出し
        max500th = ''
    count = len(vals)
    if count < 2:
        return None, None, None, count
    else:
        q1 = vals.quantile(.25)
        q3 = vals.quantile(.75)
        iqr = q3-q1
        lower_limit = q1 - iqr * 1.5
        upper_limit = q3 + iqr * 1.5
        desc = vals[(vals > lower_limit) & (vals < upper_limit)].describe() # 外れ値除去
        std = round(desc['std'], 2)
        average = round(desc['mean'], 2)
        return average, std, max500th, count
