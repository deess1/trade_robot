# -*- coding: utf-8 -*-

import datetime
import time

import MySQLdb
import MySQLdb.cursors
import traceback
import re
import os

from settings import *
from bittrex import Bittrex

bittrex = Bittrex(API_PUBLIC_KEY, API_SECRET_KEY)

class Bittrex_platform():
    _pairs = []
    _updated = None
    conn = None
    _params = {} # params for current robot/pair

    _open_orders = []  # [{'Id', 'pair', 'Quantity', 'QuantityRemaining', 'Type', 'Status', 'Limit', 'open_utime', 'close_utime'}]}
    _closed_orders = []
    _trades = []
    _fee = 0.25 # (%)
    _min_base_cur = 0.0
    
    def __init__(self, robot, robot_name, custom_pairs=None):
        try:
            self.conn = MySQLdb.connect(host=DB_SERVER, user=DB_USER, passwd=DB_PASSWD, db=DB_SCHEME, use_unicode = 1, charset = 'utf8', cursorclass=MySQLdb.cursors.DictCursor)
            c = self.conn.cursor()
            if custom_pairs:
                s= ','.join("'%s'" % i for i in custom_pairs)
                c.execute("""select s.pair FROM pump_pairs s where s.active='Y' AND pair IN (%s)""" % s)
            else:
                c.execute("""select s.pair FROM pump_pairs s where s.active='Y'""")
    
            rows = c.fetchall()
            self._pairs = [r['pair'] for r in rows]
    
            self._robot = robot
            self._robot_name = robot_name
            c.close()
        except MySQLdb.OperationalError, e:
            logger.error('Init platform: MySQL Operational Error: %s (%s)' % (e.args[0], e.args[1]))
            raise
        except:
            logger.error(traceback.format_exc())                        
        

    ######################################################################################
                
    def Execute(self):
        # set current time
        self._utime = int(time.mktime(datetime.datetime.now().timetuple()))
        for p in self._pairs:
            try:
                self._params = {}
                self._robot(self, p, self._robot_name)
            except MySQLdb.OperationalError, e:
                logger.error('execute pair: %s. MySQL Operational Error: %s (%s)' % (p, e.args[0], e.args[1]))
                break
            except:
                logger.error('execute pair: %s' % p)       
                logger.error(traceback.format_exc())                        
    
    def str2utime(self, s):
        try:
            t = int(time.mktime(time.strptime(s, '%Y-%m-%dT%H:%M:%S.%f')))
        except:
            t = int(time.mktime(time.strptime(s, '%Y-%m-%dT%H:%M:%S')))
        return t + 3600*3  # UTC -> Moscow time
    
    def order_type(self, s):
        if s=='LIMIT_BUY': return 'BUY'
        elif s=='LIMIT_SELL': return 'SELL'
        else:
            raise Exception('not supported type of order: %s' % s)
        
    ######## Platform interface ###############################################################
    
    def get_utime(self):
        return self._utime
    
    def debug(self, message):
        logger.debug(message)

    def info(self, message):
        logger.info(message)        
     
    def error(self, message):
        logger.error(message)        
            
    def load_params(self, robot, pair):
        self._params = {}
        self._current_pair = '%s-%s' % (robot, pair)
        c = self.conn.cursor()
        try:
            c.execute("""SELECT * FROM params WHERE robot=%s AND pair=%s""", [robot, pair])
            rows = c.fetchall()
            for row in rows:
                self._params[row['param']] = row['value']
        finally:
            c.close()
        
    def set_default_param(self, robot, pair, param, value):
        if self._current_pair != '%s-%s' % (robot, pair):
            raise Exception('unappropriate %s-%s'  % (robot, pair))
        if param not in self._params:
            self._params[param] = value
            c = self.conn.cursor()
            try:
                c.execute("""INSERT INTO params(robot, pair, param, value)\
                VALUES(%s,%s,%s,%s)""", [robot, pair, param, value])
            finally:
                c.close()
        
    def set_param(self, robot, pair, param, value):
        if param in self._params:
            self._params[param] = value
            c = self.conn.cursor()
            c.execute("""UPDATE params SET value=%s WHERE robot=%s AND pair=%s AND param=%s""", [value, robot, pair, param])
        else:
            raise Exception('parameter %s not defined' % param)
        
    def get_param(self, robot, pair, param):
        if self._current_pair != '%s-%s' % (robot, pair):
            raise Exception('params not loaded %s-%s'  % (robot, pair))
        
        return self._params[param]
    
    # return suspend mode
    def check_suspend(self, robot, pair):
        c = self.conn.cursor()
        try:
            c.execute("""select suspend from pump_pairs where pair=%s""", [pair])
            row = c.fetchone()
            if row and row['suspend']:
                return row['suspend']
            else:
                return NORMAL_MODE
        finally:
            c.close()
    
    def set_suspend(self, robot, pair, mode):
        c = self.conn.cursor()
        try:
            c.execute("""update pump_pairs set suspend=%s where pair=%s""", [mode, pair])
        finally:    
            c.close()
    
    def get_balance(self, cur):
        try:
            balance = bittrex.get_balance(cur)
        except:
            logger.error(traceback.format_exc())
            return
            
        if balance['success'] and balance['result']:
            try:
                return float(balance['result']['Available'])
            except:
                return 
        elif balance['message']:
            self.error('query balance: %s'  % balance['message'])
    
    # return None if error
    def get_open_orders(self, pair):
        res = []
        try:
            orders = bittrex.get_open_orders(pair)
        except:
            logger.error(traceback.format_exc())
            return
            
        if orders['success'] and orders['result']:
            for r in orders['result']:
                res += [{'Id': r['OrderUuid'], 'Quantity': r['Quantity'], 'pair': r['Exchange'], \
                         'open_utime': self.str2utime(r['Opened']), 'close_utime': None, 'QuantityRemaining': r['QuantityRemaining'],\
                         'Type': self.order_type(r['OrderType']), 'Status': 'Open', 'Price': None, 'Limit': r['Limit']}]
                
        elif orders['message']:
            self.error('get open orders: %s'  % orders['message'])
            return
         
        return res
    
    def get_open_deals_cnt(self, robot):
        c = self.conn.cursor()
        try:
            c.execute("""SELECT count(distinct pair) c FROM `params` WHERE param='state' and value in ('pump','buying', 'selling') and robot=%s""", [robot])
            row = c.fetchone()
            if row and row['c']:
                return int(row['c'])
            else:
                return 0
        finally:
            c.close()
    
    def place_order_buy(self, pair, quantity, buy_rate, limit=0.0):
        if limit==0.0:
            ticker = bittrex.get_ticker(pair)
            if ticker['success'] and ticker['result']:
                ask = float(ticker['result']['Ask'])
                limit = ask*1.5
                if ask>1.2*buy_rate:
                    return
            elif ticker['message']:
                self.error('get ticker for buy: %s'  % ticker['message'])
                return
            else:
                return
        try:
            buy = bittrex.buy_limit(pair, quantity, limit)
        except:
            logger.error(traceback.format_exc())
            return
            
        if buy['success'] and buy['result']:
            return buy['result']['uuid']
        elif buy['message']:
            self.error('place order buy: %s'  % buy['message'])
            return
        
    def place_order_sell(self, pair, quantity, sell_rate, limit=0.0):
        if limit==0.0:
            ticker = bittrex.get_ticker(pair)
            if ticker['success'] and ticker['result']:
                bid = float(ticker['result']['Bid'])
                limit = bid/1.5

            elif ticker['message']:
                self.error('get ticker for sell: %s'  % ticker['message'])
                return
            else:
                return
        
        try:
            sell = bittrex.sell_limit(pair, quantity, limit)
        except:
            logger.error(traceback.format_exc())
            return
                
        if sell['success'] and sell['result']:
            return sell['result']['uuid']
        elif sell['message']:
            self.error('place order sell: %s'  % sell['message'])
            return
    
    def get_order(self, id):
        try:
            order = bittrex.get_order(id)
        except:
            logger.error(traceback.format_exc())
            return
        
        if order['success'] and order['result']:
            r = order['result']
            try:
                res = {'Id': r['OrderUuid'], 'Quantity': r['Quantity'], 'pair': r['Exchange'], \
                             'open_utime': self.str2utime(r['Opened']), 'close_utime': self.str2utime(r['Closed']), 'QuantityRemaining': r['QuantityRemaining'],\
                             'Type': self.order_type(r['Type']), 'Status': 'Open' if r['IsOpen'] else 'Closed', 'Price': r['PricePerUnit'], 'Volume': r['Price'], 'Limit': r['Limit']}
            except:
                self.error('error get_order. it still open')
                return
            return res            
        elif order['message']:
            self.error('get order: %s'  % order['message'])
            return {}
        else:
            return {}
            
    def cancel_order(self, id):
        try:
            cancel = bittrex.cancel(id)
        except:
            logger.error(traceback.format_exc())
            return
        if cancel['success']:
            return True
        elif cancel['message']:
            self.error('cancel order: %s'  % cancel['message'])
    
dt = datetime.datetime.now()
CURRENT_TIMESTAMP = '%.2d%.2d' % (dt.month, dt.day)

LOG_FILE_ERROR = os.path.join(LOG_PATH, 'errors_robot.log')
LOG_FILE_DEBUG = os.path.join(LOG_PATH, 'debug_smart_%s.log' % CURRENT_TIMESTAMP)
LOG_FILE_INFO = os.path.join(LOG_PATH, 'trades_robot.log')

logger = logging.getLogger("robot")
logger.setLevel(logging.DEBUG)  

if logger.level == logging.DEBUG:
    debug_fh = logging.FileHandler(LOG_FILE_DEBUG)
    debug_fh.setFormatter(logging.Formatter('%(asctime)s  %(levelname)s :  %(message)s'))
    debug_fh.setLevel(logging.DEBUG)
    logger.addHandler(debug_fh)

info_fh = logging.FileHandler(LOG_FILE_INFO)
info_fh.setFormatter(logging.Formatter('%(asctime)s  %(levelname)s :  %(message)s'))
info_fh.setLevel(logging.INFO)
logger.addHandler(info_fh)

error_fh = logging.FileHandler(LOG_FILE_ERROR)
error_fh.setFormatter(logging.Formatter('%(asctime)s : [module: %(module)s; line: %(lineno)d]  %(levelname)s : %(message)s'))
error_fh.setLevel(logging.ERROR)
logger.addHandler(error_fh)
