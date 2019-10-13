import os

def database_url():
    if os.name == "nt": #ローカルの自機Windowsのとき
        return 'postgresql://srp:0000@localhost:5432/srp'
    else:
        return os.environ['DATABASE_URL']
