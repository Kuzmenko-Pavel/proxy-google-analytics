import mongo_proxy
import pymongo


def get_click_engine(config):
    safe_conn = mongo_proxy.MongoProxy(pymongo.MongoClient(config['mongo']['uri']))
    return safe_conn
