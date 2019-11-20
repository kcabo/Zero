import re

from task_manager import notify_line

time_format_ptn = re.compile(r'([0-9]{0,2}):?([0-9]{2}).([0-9]{2})')
space_erase_table = str.maketrans("","","\n\r 　 ") # 第三引数に指定した文字が削除される。左から、LF,CR,半角スペース,全角スペース,nbsp
space_and_nums = str.maketrans("","","\n\r 　 1234.")

def del_space(str):
    return str.translate(space_erase_table) if str is not None else ""

def del_numspace(str):
    return str.translate(space_and_nums)

def format_time(time_str):
    if time_str in["", "--:--.--", "-", "ｰ"]: # リレーで第一泳者以外の失格の場合--:--.--になる。最後のはハイフンではなく半角カタカナ長音
        return ""
    else:
        ob = re.match(time_format_ptn, time_str)
        # assert ob is not None, f'無効なタイム文字列:{time_str}'
        if ob is None:
            # 大会0119722の平沼さんの女子２フリはこれが適用されている
            msg = f'<!!>無効なタイム文字列＜{time_str}＞を検出しました。一時的な値として"99:99:99"を返します'
            print(msg)
            notify_line(msg)
            return '99:99.99'
        else:
            min = ob.group(1) if ob.group(1) != "" else 0 # 32.34とか分がないとき
            return f'{int(min)}:{ob.group(2)}.{ob.group(3)}'
