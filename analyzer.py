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

class Swimmer:
    pass


fmt_ptn = re.compile('([0-9]{1,2}):([0-9]{2}).([0-9]{2})') #15分とかのときは：の前は2文字になる
def fmt_2_val(fmt):
    match = re.match(fmt_ptn, fmt)
    min = int(match.group(1))
    sec = int(match.group(2)) * 100 + int(match.group(3))
    return min * 6000 + sec #100倍した秒数

def swimmer_statisctics(records):
    swimmer = Swimmer()

    # 全レコード：          id, 種目(50Fr)　スタイル　距離　記録　水路(l,m,長,短)　日付　大会名 のデータフレームを作成
    fixed = map(lambda x:(x.Record.id, x.Record.style, x.Record.distance, '', x.Record.time, x.Meet.pool, x.Meet.start, x.Meet.name), records)
    df = pd.DataFrame(fixed, columns = ['id', 'style', 'distance', 'event', 'time', 'pool', 'start', 'meet_name'])
    df['pool'] = df['pool'].map(lambda x:'l' if x == 1 else 's')
    df['style'] = df['style'].map(num_2_style)
    df['distance'] = df['distance'].map(num_2_distance)
    df['event'] = df['distance'].astype(str) + df['style']

    swimmer.records = df.sort_values(['start', 'style', 'distance', 'time'], ascending=[False, True, True, True])
    df = df[df['time'] != ""] # 空白タイム削除

    # 出場回数：            全出場回数　五スタイルのそれぞれの回数(リストか辞書)　スタイルと距離を結合（種目）し、そのなかでの最多(S1)　偏差値(保留)
    swimmer.total_count = len(df)
    # ['Fr', 'Ba', 'Br', 'Fly', 'IM'] の順のリストを２つ
    def count_style(df, pool):
        filtered = df[df['pool'] == pool]
        dic = filtered['style'].value_counts().to_dict()
        return [dic.get(s, 0) for s in ['Fr', 'Ba', 'Br', 'Fly', 'IM']]

    swimmer.count_style_long = count_style(df, "l")
    swimmer.count_style_short = count_style(df, "s")

    # 上の段階で折れ線グラフ化する2種目を選ぶ ←S1のスタイルのなかから、もっとも出場している種目を2つ選ぶ ←今後３つとかにしてもいいよね
    swimmer.s1 = df['event'].value_counts().index[0] # ここでのS1はスタイルではなく距離も含めた種目
    swimmer.s2 = df['event'].value_counts().index[1]

    # 調子折れ線グラフ：     2種目2水路に分ける。日付のシリアル化。記録の並び替え（1:経過日数少ない順,2:タイム早い順）して、日数が被ってるのを重複削除
    from_date = datetime.datetime(2019,4,1)
    df['days'] = df['start'].map(lambda x: (datetime.datetime.strptime(x, '%Y/%m/%d') - from_date).days) # 日付のシリアル化
    df['time_val'] = df['time'].map(fmt_2_val)

    def set_scatter_points(df, event, pool):
        filtered = df[(df['event'] == swimmer.s1) & (df['pool'] == pool)].loc[:, ['days', 'time_val']]
        filtered.sort_values(['days','time_val'], inplace=True)
        filtered.drop_duplicates(subset='days', inplace=True)
        if len(filtered) == 0:
            return ''
        elif len(filtered) == 1:
            return '{{x:{filtered["days"].iloc[0]},y:50}}'
        else:
            max = filtered['time_val'].max()
            min = filtered['time_val'].min()
            filtered['normalized'] = filtered['time_val'].map(lambda x:((max - x)*100)/(max - min))
            points = [f"{{x:{days},y:{int(normalized)}}}" for days, normalized in zip(filtered['days'], filtered['normalized'])]
            return ','.join(points)

    swimmer.e1_long_points = set_scatter_points(df, swimmer.s1, 'l')
    swimmer.e1_short_points = set_scatter_points(df, swimmer.s1, 's')
    swimmer.e2_long_points = set_scatter_points(df, swimmer.s2, 'l')
    swimmer.e2_short_points = set_scatter_points(df, swimmer.s2, 's')

    #                      タイムを数値変換。最大値(最遅)からそれぞれの記録を引き算。その結果の中での最大値(最速)をdとし100/dをそれぞれに乗算
    #                      {x:経過日数,y:計算結果}のリストを返す。それを4回繰り返す。


    # データフレームを（早い順、日付最新順）に並び替え。種目で重複削除。
    # 6カテゴリ(5種目＋長距離)の変数を作る。型はリストかディクショナリ。すべての抽出結果をその中に格納。（ベストのないカテゴリはFalseを返すようにする）

    return swimmer
