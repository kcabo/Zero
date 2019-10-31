# models.pyからインポートされる
# from models import Meet, Record, Relay
import constant

import os
import re
import requests

from bs4 import BeautifulSoup, element
from tqdm import tqdm

meet_link_ptn = re.compile(r"code=[0-9]{7}$") # <a href="../../swims/ViewResult?h=V1000&amp;code=0119605"
meet_caption_ptn = re.compile(r"(.+)　（(.+)） (.水路)") # 茨城:第42回県高等学校春季　（取手ｸﾞﾘｰﾝｽﾎﾟｰﾂｾﾝﾀｰ） 長水路
event_link_ptn = re.compile(r"&code=(\d{7})&sex=(\d)&event=(\d)&distance=(\d)") # "/swims/ViewResult?h=V1100&code=0919601&sex=1&event=5&distance=4"
time_format_ptn = re.compile(r'([0-9]{0,2}):?([0-9]{2}).([0-9]{2})')

space_erase_table = str.maketrans("","","\n\r 　 ") # 第三引数に指定した文字が削除される。左から、LF,CR,半角スペース,全角スペース,nbsp
space_and_nums = str.maketrans("","","\n\r 　 1234.")

def del_space(str):
    return str.translate(space_erase_table) if str is not None else ""

def del_numspace(str):
    return str.translate(space_and_nums)

def format_time(time_str):
    if time_str == "" or time_str == "--:--.--" or time_str == "-": # リレーで第一泳者以外の失格の場合--:--.--になる
        return ""
    else:
        ob = re.match(time_format_ptn, time_str)
        if ob is None: # おそらく発生しないはず。すべて正規表現に一致するはず
            print('\n>>無効なタイム文字列:{}'.format(time_str))
            return time_str
        else:
            min = ob.group(1) if ob.group(1) != "" else 0 # 32.34とか分がないとき
            return "{}:{}.{}".format(min, ob.group(2), ob.group(3))

# DOM探索木をURLから生成
def pour_soup(url):
    req = requests.get(url)
    req.encoding = "cp932"
    return BeautifulSoup(req.text, "lxml")

# class Meet(db.Model):
#     __tablename__ = 'meets'
#     id = db.Column(db.Integer, primary_key=True)                      # 連番で振られるid
#     meetid = db.Column(db.String, unique = True, nullable = False)    # 7桁の大会ID 0119721など0で始まることもある
#     name = db.Column(db.String, nullable = False)                     # 大会名
#     place = db.Column(db.String, nullable = False)                    # 会場
#     pool = db.Column(db.String, nullable = False)                     # 短水路or長水路
#     start = db.Column(db.String, nullable = False)                    # 大会開始日 2019/09/24 で表す
#     end = db.Column(db.String, nullable = False)                      # 大会終了日
#     area = db.Column(db.Integer, nullable = False)                    # 地域(整数)
#     year = db.Column(db.Integer, nullable = False)                    # 開催年
#     code = db.Column(db.Integer, nullable = False)                    # 下三桁

def meet_init_func(self, meet_id): # meetidを受け取り大会情報を持たせる
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
    self.pool = matchOb.group(3)

# コンストラクタを後から追加
Meet.__init__ = meet_init_func



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


# class Record(db.Model): #個人種目の１記録
#     __tablename__ = 'records'
#     id = db.Column(db.Integer, primary_key=True)                      # 連番で振られるid
#     meetid = db.Column(db.String, nullable = False)                   # 7桁の大会ID 0119721など0で始まることもある
#     sex = db.Column(db.Integer, nullable = False)                     # 性別
#     style = db.Column(db.Integer, nullable = False)                   # 泳法
#     distance = db.Column(db.Integer, nullable = False)                # 距離
#     name = db.Column(db.String, nullable = False)                     # 選手氏名
#     team = db.Column(db.String, nullable = False)                     # 所属名
#     grade = db.Column(db.String, nullable = False)                    # 学年
#     time = db.Column(db.String, nullable = False)                     # タイム。#:##.##書式文字列
#     laps = db.Column(db.String, nullable = False)                     # ラップタイム。#:##.##,#:##.##,...

def record_init_func(self, meet_id, sex, style, distance, row, lap_table):
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

def fix_raw_record_data(self):
    self.name = del_space(self.name)
    self.team = del_space(self.team)
    self.grade = del_space(self.grade)
    self.time = format_time(del_space(self.time))
    self.laps = ",".join([format_time(del_space(lap)) for lap in self.laps])

Record.__init__ = record_init_func
Record.fix_raw_data = fix_raw_record_data



# class Relay(db.Model): #リレーの結果
#     __tablename__ = 'relay'
#     id = db.Column(db.Integer, primary_key=True)                      # 連番で振られるid
#     meetid = db.Column(db.String, nullable = False)                   # 7桁の大会ID 0119721など0で始まることもある
#     sex = db.Column(db.Integer, nullable = False)                     # 性別
#     style = db.Column(db.Integer, nullable = False)                   # 泳法
#     distance = db.Column(db.Integer, nullable = False)                # 距離
#     rank = db.Column(db.String, nullable = False)                     # 順位（棄権や失格の場合も記述される）
#     team = db.Column(db.String, nullable = False)                     # 所属名
#     time = db.Column(db.String, nullable = False)                     # タイム。#:##.##書式文字列
#     laps = db.Column(db.String, nullable = False)                     # ラップタイム。#:##.##,#:##.##,...
#     name_1 = db.Column(db.String, nullable = False)                   # 第一泳者
#     name_2 = db.Column(db.String, nullable = False)                   # 第二泳者
#     name_3 = db.Column(db.String, nullable = False)                   # 第三泳者
#     name_4 = db.Column(db.String, nullable = False)                   # 第四泳者
#     grade_1 = db.Column(db.String, nullable = True)                   # 第一泳者の学年
#     grade_2 = db.Column(db.String, nullable = True)                   # 第二泳者の学年
#     grade_3 = db.Column(db.String, nullable = True)                   # 第三泳者の学年
#     grade_4 = db.Column(db.String, nullable = True)                   # 第四泳者の学年

def relay_init_func(self, meet_id, sex, style, distance, row, lap_table):
    self.meetid = meet_id
    self.sex = sex
    self.style = style
    self.distance = distance
    data = row.find_all("td")
    self.rank = data[0].text # data[0].stringだとタグを含んだときにNoneが返されてしまう
    swimmers = [del_numspace(name) for name in data[1].contents if isinstance(name, element.NavigableString)] # data[1].contentsはbrタグを含む配列
    count_swimmers = len(swimmers)
    if count_swimmers !=4 and count_swimmers!=1: # おそらく発生しない
        print(data[1])
        raise IndexError("泳者が４人でも空白スペースだけでもありません！")
    self.name_1 = swimmers[0] if count_swimmers == 4 else ""
    self.name_2 = swimmers[1] if count_swimmers == 4 else ""
    self.name_3 = swimmers[2] if count_swimmers == 4 else ""
    self.name_4 = swimmers[3] if count_swimmers == 4 else ""
    self.team = data[2].string
    self.time = data[3].a.string if data[3].a is not None else ""
    laps = lap_table.find_all("td", width = True)
    self.laps = [lap.string for lap in laps]

def fix_raw_relay_data(self):
    self.rank = del_space(self.rank)
    self.team = del_space(self.team)
    self.time = format_time(del_space(self.time))
    self.laps = ",".join([format_time(del_space(lap)) for lap in self.laps])

Relay.__init__ = relay_init_func
Relay.fix_raw_data = fix_raw_relay_data


# 特定の年度・地域で開催された大会IDのリストを作成するサブルーチン
def find_meet(year, area):
    url = r"http://www.swim-record.com/taikai/{}/{}.html".format(year, area)
    soup = pour_soup(url)
    #div内での一番最初のtableが競泳、そのなかでリンク先がコードになっているものを探す
    meet_id_aTags = soup.find("div", class_ = "result_main").find("table", recursive = False).find_all("a", href = meet_link_ptn)
    id_list = [a["href"][-7:] for a in meet_id_aTags] #大会コード七桁のみ抽出
    return id_list

# 大会のインスタンス集合から種目のインスタンス集合を作るサブルーチン
def arrange_events(target_meets):
    events = []
    print("{}の大会の全開催種目を集めています…".format(len(target_meets)))
    for meet in tqdm(target_meets):
        soup = pour_soup("http://www.swim-record.com/swims/ViewResult/?h=V1000&code=" + meet.meetid)
        aTags = soup.find_all("a", class_=True)             # 100m自由形などへのリンク
        events.extend([Event(a["href"]) for a in aTags])    # リンクから種目のインスタンス生成
        print("{}種目見つかりました。".format(len(events)))       # 25690 10min-1390meets
        return events

# 指定年度の大会の情報をDBに追加
def fetch_meets(year):
    print("{}年の大会IDを集めています…".format(year))
    meet_ids = []
    for area in tqdm(constant.area_list):
        meet_ids.extend(find_meet(year, area))

    print(f'20{year}年に開催される{len(meet_ids)}の大会の情報を取得しています…')
    meets = [Meet(id) for id in tqdm(meet_ids)]
    return meets # DBへの追加はメインで



def fetch_records(target_meets): # 対象の大会のインスタンス集合を受け取りそれらの記録すべて返す
    # target_meets = session.query(Meet).filter(Meet.start >= "2019/06/25", Meet.start <= "2019/07/30").all()
    # target_meets = session.query(Meet).filter(Meet.meetid == meetid).all()
    # target_meets = session.query(Meet).filter(Meet.start >= minDate).all()
    # target_meets = session.query(Meet).all()
    events = arrange_events(target_meets)
    records = []
    print('記録の抽出を開始します...')
    for e in tqdm(events):
        table, lap_tables = e.parse_table()
        if e.style <= 5: # 個人種目＝自由形・背泳ぎ・平泳ぎ・バタフライ・個人メドレー
            records.extend([Record(e.meet_id, e.sex, e.style, e.distance, row, lap_table) for row, lap_table in zip(table, lap_tables)])
        else:
            records.extend([Relay(e.meet_id, e.sex, e.style, e.distance, row, lap_table) for row, lap_table in zip(table, lap_tables)])
    print('{}個の記録が見つかりました。\nデータを適切な形に編集しています...'.format(len(records)))
    for r in records:
        r.fix_raw_data()
    return records # DBへの追加はメインで

# if __name__ == '__main__':
#     # create_table()
#     # fetch_meets(19)
#     # fetch_records()
#     # pass
#     q = session.query(Record, Meet).join(Meet, Record.meetid == Meet.meetid).all()
#     # q = session.query(Record).distinct(Record.grade).all()
#
#
#     for q_ in q[5004:5100]:
#         print(q_.Record)
#         print(q_.Meet)