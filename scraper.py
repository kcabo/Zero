import re
import requests
from time import sleep

from bs4 import BeautifulSoup, element

import format

meet_link_ptn = re.compile(r"code=[0-9]{7}$")           # <a href="../../swims/ViewResult?h=V1000&amp;code=0119605"
meet_caption_ptn = re.compile(r"(.+)　（(.+)） (.水路)") # 茨城:第42回県高等学校春季　（取手ｸﾞﾘｰﾝｽﾎﾟｰﾂｾﾝﾀｰ） 長水路
event_link_ptn = re.compile(r"&code=(\d{7})&sex=(\d)&event=(\d)&distance=(\d)") # "/swims/ViewResult?h=V1100&code=0919601&sex=1&event=5&distance=4"

# DOM探索木をURLから生成
def make_soup(url):
    sleep(1) # 負荷軽減用
    req = requests.get(url)
    req.encoding = "cp932"
    return BeautifulSoup(req.text, "lxml")

def meet_info(meet_id):
    url = f'http://www.swim-record.com/swims/ViewResult/?h=V1000&code={meet_id}'
    soup = make_soup(url)
    caption = soup.find("div", class_ = "headder").find_all("td", class_ = "p14b")

    # 2019/04/27 - 2019/04/27  ←caption[0]
    date = caption[0].string
    start = date[:10]
    end = date[-10:]

    # 茨城:第42回県高等学校春季　（取手ｸﾞﾘｰﾝｽﾎﾟｰﾂｾﾝﾀｰ） 長水路  ←caption[1]
    meet_title = re.match(meet_caption_ptn, caption[1].string)
    name = meet_title.group(1)
    place = meet_title.group(2)
    pool = 0 if meet_title.group(3)=='短水路' else 1

    return start, end, name, place, pool


# 特定の年度・地域で開催された大会IDのリストを作成するサブルーチン
def find_meet(year, area):
    url = f"http://www.swim-record.com/taikai/{year}/{area}.html"
    soup = make_soup(url)
    #div内での一番最初のtableが競泳大会表。特定パターンのリンクを探す
    meet_id_aTags = soup.find("div", class_ = "result_main").find("table", recursive = False).find_all("a", href = meet_link_ptn)
    id_list = [a["href"][-7:] for a in meet_id_aTags] #大会コード七桁のみ抽出
    return id_list

class Event:
    def __init__(self, link):   # 一種目の情報とURL 1種目の結果一覧画面に紐付けられている
        matchOb = re.search(event_link_ptn, link) # link = "/swims/ViewResult?h=V1100&code=0919601&sex=1&event=5&distance=4"
        self.meet_id = matchOb.group(1)
        self.url = "http://www.swim-record.com" + link
        self.sex = int(matchOb.group(2))
        self.style = int(matchOb.group(3))
        self.distance = int(matchOb.group(4))
        self.is_indivisual = self.style <= 5 # 個人種目(自由形・背泳ぎ・平泳ぎ・バタフライ・個人メドレー)なら

    def all_records(self): # 記録一覧のページの表を全部とってくる
        soup = make_soup(self.url)
        rows = soup.find_all("tr", align = "center", bgcolor = False)       # 中央寄せでbgcolorの引数を持たない= レコード行
        lap_tables = soup.find_all("tr", align = "right", id = True, style = True) # それぞれのtr内にLAPSテーブルが格納されている
        set_of_args = []
        for row, lap_table in zip(rows, lap_tables):
            data = row.find_all("td") # 一行の中に複数のtd(順位、氏名…)(リレーと個人で異なる)が格納されている
            laps_raw = lap_table.find_all("td", width = True) # タイムの書かれたtdのみがwidthの引数を持つ
            laps = [format.del_space(l.string) for l in laps_raw] # タグを取り除く
            laps_format = ",".join([format.format_time(l) for l in laps])

            if self.is_indivisual:
                grade = format.del_space(data[3].string)
                time_raw = data[4].a
                name = format.del_space(data[1].string)
            else:
                grade = '' # リレーに学年は存在しない
                time_raw = data[3].a
                # data[1].contentsはbrタグを含む配列 タグ以外をswimmersに格納
                names = [format.del_numspace(name) for name in data[1].contents if isinstance(name, element.NavigableString)]
                count = len(names)
                assert count == 1 or count == 4
                if count == 4:
                    name = (names[0], names[1], names[2], names[3])
                else: # リレーを棄権したため氏名の表記が無いとき、改行文字だけが検出され、要素数1となる
                    name = ('', '', '', '')
            rank = format.del_space(data[0].text) # data[0].stringだとタグを含んだときにNoneが返されてしまう
            team = format.del_space(data[2].string)
            time = '' if time_raw is None else format.del_space(time_raw.string)
            time_format = format.format_time(time)

            # レコードインスタンスを作るのに必要な引数をまとめたタプル
            arguments_for_single_record = (self.meet_id, self.sex, self.style, self.distance, rank, name, team, grade, time_format, laps_format)
            set_of_args.append(arguments_for_single_record)
        return set_of_args

def result_links_in_meet_page(meet_id):
    url = f'http://www.swim-record.com/swims/ViewResult/?h=V1000&code={meet_id}'
    soup = make_soup(url)
    aTags = soup.find_all("a", class_=True)             # 100m自由形などへのリンクをすべてリストに格納
    links = [a['href'] for a in aTags]
    return links

def all_events(meet_id):
    # 大会IDを指定し、そこから全開催種目を抜き出す。そしてそれらをEventインスタンスにする
    # つまりひとつの大会内での全種目の情報を返す
    return [Event(link) for link in result_links_in_meet_page(meet_id)]
