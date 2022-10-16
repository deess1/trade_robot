# -*- coding: utf-8 -*-

import datetime
import time

from settings import *
from bittrex import Bittrex
import MySQLdb
import MySQLdb.cursors
import traceback
import os
from requests.exceptions import ConnectionError

LOAD_VOLUME = False 

INTERVAL = 300
PARAM_TYPE = 'Ticket'
PARAM_NAME = 'last_run'

bittrex = Bittrex(None, None)

def str2utime(s):
    try:
        t = int(time.mktime(time.strptime(s, '%Y-%m-%dT%H:%M:%S.%f')))
    except:
        t = int(time.mktime(time.strptime(s, '%Y-%m-%dT%H:%M:%S')))
    return t + 3600*3  # UTC -> Moscow time


def load_ticker(curs, pair, interval):
    cur_time = int(time.mktime(datetime.datetime.now().timetuple()))
    curs.execute("""SELECT * FROM params WHERE robot=%s AND pair=%s AND param=%s""", [PARAM_TYPE, pair, PARAM_NAME])
    row = c.fetchone()
    if not row: return
    
    last_run = int(row['value'])
    
    if cur_time-last_run<int(interval*0.95):
        #logger.debug('Pair: %s: Last run: %d, Current Timestamp: %d. Period not reached. exit' % (pair, last_run, cur_time))
        return

    try:
        ticker = bittrex.get_ticker(pair)
    except:
        logger.debug('Pair: %s,  network error get ticker. exit' % pair)
        return
    
    if ticker['success'] and ticker['result']:
        try:
            curr_buy_rate = float(ticker['result']['Ask'])
            curr_sell_rate = float(ticker['result']['Bid'])
            
            c.execute("""INSERT INTO tickers(pair, updated, buy, sell)\
            VALUES(%s, %s, %s, %s)""", [pair, cur_time, curr_buy_rate, curr_sell_rate ])
            
            c.execute("""UPDATE params SET value=%s WHERE robot=%s AND pair=%s AND param=%s""", [cur_time, PARAM_TYPE, pair, PARAM_NAME])
        except MySQLdb.Error, e:
            logger.error('Pair: %s,  insert into tickers error: %s' % (pair, e[1]))
            return
        except Exception, e:
            logger.error('Pair: %s,  insert into tickers other error: %s' % (pair, e.message))
            return
    else:
        if ticker['message']: logger.error('Pair: %s,  get_ticker: %s' % (pair, ticker['message']))
        return
    
    if not LOAD_VOLUME:
        return
    #logger.debug('load_history')
    try:    
        history = bittrex.get_market_history(pair, 200)
    except ValueError, ConnectionError:
        logger.error('get_market_history unavailable')
        return
        
    if history['success'] and history['result']:
        buy_vol = 0.0
        sell_vol = 0.0
        for rec in history['result']:
            t = str2utime(rec['TimeStamp'])
            if t<=cur_time and t>=cur_time-interval:
                if rec['OrderType']=='SELL':
                    sell_vol += float(rec['Total'])
                elif rec['OrderType']=='BUY': 
                    buy_vol += float(rec['Total'])
            elif t<cur_time-interval:
                break

        try:
            c.execute("""UPDATE tickers SET buy_vol=%s, sell_vol=%s\
            WHERE pair=%s AND updated=%s""", [buy_vol, sell_vol, pair, cur_time])
        except MySQLdb.Error, e:
            logger.error('Pair: %s,   update tickers volume error: %s' % (pair, e[1]))
        except Exception, e:
            logger.error('Pair: %s,   update tickers other error: %s' % (pair, e.message))
            return        
    else:
        if ticker['message']: logger.error('Pair: %s,   get_market_history: %s' % (pair, history['message']))


LOG_FILE_ERROR = os.path.join(LOG_PATH, 'errors_tickers.log')
LOG_FILE_DEBUG = os.path.join(LOG_PATH, 'debug_tickers.log')

logger = logging.getLogger("ticker")
logger.setLevel(logging.INFO)  

if logger.level == logging.DEBUG:
    debug_fh = logging.FileHandler(LOG_FILE_DEBUG)
    debug_fh.setFormatter(logging.Formatter('%(asctime)s  %(levelname)s :  %(message)s'))
    debug_fh.setLevel(logging.DEBUG)
    logger.addHandler(debug_fh)

error_fh = logging.FileHandler(LOG_FILE_ERROR)
error_fh.setFormatter(logging.Formatter('%(asctime)s : [module: %(module)s; line: %(lineno)d]  %(levelname)s : %(message)s'))
error_fh.setLevel(logging.ERROR)
logger.addHandler(error_fh)


start_time = int(time.mktime(datetime.datetime.now().timetuple()))
conn = MySQLdb.connect(host=DB_SERVER, user=DB_USER, passwd=DB_PASSWD, db=DB_SCHEME, use_unicode = 1, charset = 'utf8', cursorclass=MySQLdb.cursors.DictCursor)
c = conn.cursor()

# check and add new pair params
c.execute("""select s.pair FROM pump_pairs s where s.active='Y' and not exists(select * from params p where p.pair=s.pair and p.robot=%s and p.param=%s)""", [PARAM_TYPE, PARAM_NAME])
rows = c.fetchall()
for row in rows:
    c.execute("""INSERT INTO params(robot, pair, param, value) values(%s, %s, %s, 0)""", [PARAM_TYPE, row['pair'], PARAM_NAME])    

c.execute("""select s.pair FROM pump_pairs s, params p where s.active='Y' and p.pair=s.pair and p.robot=%s and p.param=%s order by p.value""", [PARAM_TYPE, PARAM_NAME])
rows = c.fetchall()
#logger.debug('Start pump robot. check %d pairs' % len(rows))
cnt = 0
for row in rows:
    if int(time.mktime(datetime.datetime.now().timetuple()))-start_time>40:
        logger.debug('Time limit reached. %d pairs processed' % cnt)
        break
    try:            
        load_ticker(c, row['pair'], INTERVAL)
        cnt += 1
    except:
        logger.error('pair: %s' % row['pair'])       
        logger.error(traceback.format_exc())