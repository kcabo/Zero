import re

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
        assert ob is not None, f'無効なタイム文字列:{time_str}'
        min = ob.group(1) if ob.group(1) != "" else 0 # 32.34とか分がないとき
        return f'{min}:{ob.group(2)}.{ob.group(3)}'
