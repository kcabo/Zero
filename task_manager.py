from time import time

class Takenoko:
    # tqdmみたいなイテレータ。要はプログレスバー
    # タケノコに見えないのはご愛嬌
    def __init__(self, list):
        self.start = time()
        self.list = list
        self.current = 0 # 処理中のインデックス
        self.grow = 0 # タケノコの成長具合
        self.length = len(list)
        # リスト全体を10等分し、途中通過地点を格納したリストを作成
        interval = self.length / 10
        self.process = [int(i * interval)-1 for i in range(1,11)]

    # まず__iter__メソッドが呼ばれてから__next__が呼ばれる
    def __iter__(self):
        return self

    def __next__(self):
        index = self.current
        max = self.length
        if index >= max:
            elapsed = time() - self.start
            print(f'>>> Done!  length: {max}  minutes: {round(elapsed/60)}')
            raise StopIteration()
        elif index >= self.process[self.grow]:
            self.grow += 1
            msg = '|{:10s}|{:^5d}in {}'.format('*' * self.grow, index + 1, max)
            print(msg)
        self.current += 1
        return self.list[index]

path = 'status'
def update_status(status):
    with open(path, 'w') as f:
        f.write(status)
    print(f'status updated: {status}')

def free():
    update_status('free')

def busy():
    update_status('busy')

def get_status():
    with open(path, 'r') as f:
        status = f.read()
    if status not in ['busy', 'free']:
        raise Exception('ステータスファイルの値が無効です！')
    return status
