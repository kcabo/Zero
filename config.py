import os

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://srp:0000@localhost:5432/srp')
LINE_TOKEN = os.environ.get('LINE_NOTIFY_ACCESS_TOKEN', None)
REDIS_URL = os.environ.get('REDIS_URL', 'redis://@localhost:6379/0')
ADMIN_URL = os.environ.get('ADMIN_URL', '')


class Base:
    SQLALCHEMY_DATABASE_URI = DB_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False #これ書かないとログがうるさくなる
    TESTING = True

class Develop(Base):
    DEBUG = True

class Product(Base):
    DEBUG = False
