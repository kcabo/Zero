import datetime
import pandas as pd
import os
import re

from constant import japanese_grades

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

def val_2_fmt(val):
    if val > 0:
        min = val // 6000
        hecto_seconds = val % 6000
        sec = hecto_seconds // 100
        centi_sec = hecto_seconds % 100
        return f'{min}:{format(sec,"02")}.{format(centi_sec,"02")}'
    else:
        return ''

class Swimmer:
    def __init__(self, records):
        converted = map(lambda x:(x.Record.id,
                            x.Record.event,
                            x.Record.time,
                            'l' if x.Meet.pool == 1 else 's',
                            x.Meet.start,
                            x.Meet.name), records)

        # 全レコード：id, 種目 百倍秒数　水路(l,m)　日付(整数)　大会名 のデータフレームを作成
        df = pd.DataFrame(converted, columns = ['id', 'event_val', 'time_val', 'pool', 'start', 'meet_name'])
        df['style'] = df['event_val'].map(lambda x : num_2_style[(x // 10) % 10])      # 3桁のeventのうちの真ん中の桁(泳法)を取り出し文字列に変換
        df['distance'] = df['event_val'].map(lambda x : num_2_distance[x % 10])        # 3桁のうち1の位の距離を取り出し文字列変換
        df['event'] = df['distance'].astype(str) + df['style']                         # 距離を文字列変換してから結合→50Frの形に
        df['time'] = df['time_val'].map(val_2_fmt) # 読める形にフォーマット
        df['start'] = df['start'].map(lambda x: datetime.datetime.strptime(str(x), '%Y%m%d').strftime('%Y/%m/%d'))

        self.records = df.sort_values(['start', 'event_val', 'time_val'], ascending=[False, True, True]) # 日付のみ新しい順に
        df = df[df['time_val'] > 0] # 空白タイム削除

        self.total_count = len(df)
        self.count_style_long = self.count_style(df, "l") # 各種目に何回出場したか
        self.count_style_short = self.count_style(df, "s")

        # 折れ線グラフ化する最多出場の2種目を選ぶ ここでのS1はスタイルではなく距離も含めた種目
        event_counts = df['event'].value_counts()
        s1 = event_counts.index[0] if len(event_counts) > 0 else ''  # 出場種目が棄権しか無いと得意種目すら無い
        s2 = event_counts.index[1] if len(event_counts) > 1 else ''  # 1種目しか出場しておらずS2が無いときは空白
        self.s1 = {'event_name': s1}
        self.s1['event_number'] = df[df['event']==s1].iloc[0]['event_val'] # 偏差値導出用のEventnumber
        self.s2 = {'event_name': s2}

        from_date = datetime.datetime(2019,4,1) # 経過日数の基準となる日付
        df['days'] = df['start'].map(lambda x: (datetime.datetime.strptime(x, '%Y/%m/%d') - from_date).days) # 日付のシリアル化 基準日からの経過日数
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


    def count_style(self, df, pool): # ['Fr', 'Ba', 'Br', 'Fly', 'IM'] の順で出現頻度のリストを生成
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
        grade = df.iloc[0]['grade']
        self.grade = japanese_grades[grade]
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

def format_grade_and_time(df):
    df['time'] = df['time_val'].map(val_2_fmt)
    df['grade'] = df['grade'].map(lambda x: japanese_grades[x])
    return df

def output_ranking(records):
    fixed = map(lambda x:(x.Record.id, x.Record.name, x.Record.team, x.Record.grade, x.Record.time), records)
    df = pd.DataFrame(fixed, columns = ['id', 'name', 'team', 'grade', 'time_val'])
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
