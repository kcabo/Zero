import pandas as pd

class Swimmer:
    pass

def swimmer_statisctics(records):


    # 全レコード：          id, 種目(50Fr)　スタイル　距離　記録　水路(l,m,長,短)　日付　大会名 のデータフレームを作成
    fixed = map(lambda x:(x.Record.id, x.Record.style, x.Record.distance, x.Record.time, x.Meet.pool, x.Meet.start, x.Meet.name), records)
    df = pd.DataFrame(fixed, columns = ['id', 'style', 'distance', 'time', 'pool', 'start', 'meet_name'])
    # print(df)

    # 出場回数：            全出場回数　五スタイルのそれぞれの回数(リストか辞書)　スタイルと距離を結合（種目）し、そのなかでの最多(S1)　偏差値(保留)

    # 上の段階で折れ線グラフ化する2種目を選ぶ ←S1のスタイルのなかから、もっとも出場している種目を2つ選ぶ ←今後３つとかにしてもいいよね
    # 調子折れ線グラフ：     2種目2水路に分ける。日付のシリアル化。記録の並び替え（1:経過日数少ない順,2:タイム早い順）して、日数が被ってるのを重複削除
    #                      タイムを数値変換。最大値(最遅)からそれぞれの記録を引き算。その結果の中での最大値(最速)をdとし100/dをそれぞれに乗算
    #                      {x:経過日数,y:計算結果}のリストを返す。それを4回繰り返す。
    # データフレームを（早い順、日付最新順）に並び替え。種目で重複削除。
    # 6カテゴリ(5種目＋長距離)の変数を作る。型はリストかディクショナリ。すべての抽出結果をその中に格納。（ベストのないカテゴリはFalseを返すようにする）
