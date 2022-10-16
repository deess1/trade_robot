# -*- coding: utf-8 -*-
import datetime
import time

import MySQLdb
import MySQLdb.cursors
import traceback
import re
import os

from settings import *
from pump_robot import CSmartRobot
from deep_robot import CDeepRobot

BASE_CURRENCY = 'BTC'

class CPumpSimul():
    _pairs = []
    _updated = None
    conn = None
    _params = {}    # {'robot': {'pair': {'param': value} } }
    _funds = {}     # {'BTC': 0.12, 'VTC': 1.23, ...}

    _current_order_id = 1    
    _open_orders = []  # [{'Id', 'pair', 'Quantity', 'QuantityRemaining', 'Type', 'Status', 'Limit', 'open_utime', 'close_utime'}]}
    _closed_orders = []
    _trades = []
    _fee = 0.25 # (%)
    _min_base_cur = 0.0
    _trade_cnt = 0
    _max_trade_cnt = 0
    
    def __init__(self, robot, robot_name, custom_pairs=None):
        self.conn = MySQLdb.connect(host=DB_SERVER, user=DB_USER, passwd=DB_PASSWD, db=DB_SCHEME, use_unicode = 1, charset = 'utf8', cursorclass=MySQLdb.cursors.DictCursor)
        c = self.conn.cursor()
        if custom_pairs:
            s= ','.join("'%s'" % i for i in custom_pairs)
            c.execute("""select s.pair FROM pump_pairs s where s.active='Y' AND pair IN (%s)""" % s)
        else:
            c.execute("""select s.pair FROM pump_pairs s where s.active='Y'""")

        rows = c.fetchall()
        self._pairs = [r['pair'] for r in rows]
        self._funds[BASE_CURRENCY] = 0.0
        self._current_order_id = 1
        for p in self._pairs:
            cur = p.replace('%s-' % BASE_CURRENCY, '')
            self._funds[cur] = 0.0

        self._robot = robot
        self._robot_name = robot_name
        c.execute("""DELETE FROM pump_deals WHERE robot=%s""", [self._robot_name])
        #c.execute("""DELETE FROM pump_deals2 WHERE robot=%s""", [self._robot_name])
        #c.execute("""DELETE FROM drop_activity""")
        
        c.close()
        self._force_mode = False

    ######## Simulator interface ############################################################
    def getInfo(self):
        sum = self._funds[BASE_CURRENCY]
        c = self.conn.cursor()
        other = {}
        for cur in self._funds:
            if cur!=BASE_CURRENCY and self._funds[cur]>0.0:
                other[cur] = self._funds[cur]
                c.execute("""select buy, sell FROM tickers where pair=%s order by updated desc limit 1""", ['%s-%s' % (BASE_CURRENCY, cur)])
                price = c.fetchone()
                sum += price['sell']*other[cur] 
        
        c.close()        
            
        return {'total %s funds' % BASE_CURRENCY: sum, 'max trade cnt': self._max_trade_cnt, 'clear %s funds' % BASE_CURRENCY: self._funds[BASE_CURRENCY], 'other funds:': other, 'closed orders': len(self._closed_orders), 'min balance': self._min_base_cur}

    def setBalance(self, cur, amt):
        self._funds[cur] = amt
        self._min_base_cur = amt
                
    def Execute(self, start_date, end_date, time_interval=300):
        c = self.conn.cursor()
        start_utime = int(time.mktime(start_date.timetuple()))
        end_utime = int(time.mktime(end_date.timetuple()))
        self._utime = start_utime   
        last_prc = 0.0
        while self._utime<end_utime:
            #c.execute("""select sum(sell) sell FROM tickers where pair<>'USDT-BTC' and updated between %s and %s""", [self._utime-time_interval, self._utime])
            
            if self._utime>end_utime-3600:
                self._force_mode = True
            curr_prc = 100.0*(self._utime-start_utime)/float(end_utime-start_utime)
            if curr_prc>last_prc+5.0:
                print 'Proceed: %.2f%%' % curr_prc
                last_prc=curr_prc
                 
            #self._robot(self, self._pairs[0])
            for p in self._pairs:
                self._robot(self, p, self._robot_name)
            
            self.process_orders()
            self._utime += time_interval
    
    ######## Platform interface ###############################################################
    
    def get_utime(self):
        return self._utime
    
    def debug(self, message):
        logger.debug(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._utime))+'  DEBUG :  ' + message)

    def info(self, message):
        logger.info(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._utime))+'  INFO :  ' + message)        
     
    def error(self, message):
        logger.error(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._utime))+'  ERROR :  ' + message)        
            
    def load_params(self, robot, pair):
        None
        
    def set_default_param(self, robot, pair, param, value):
        if robot in self._params and pair in self._params[robot] and param in self._params[robot][pair]:
            return
        if not robot in self._params:
            self._params[robot] = {}
        
        if not pair in self._params[robot]:
            self._params[robot][pair] = {}
            
        if not param in self._params[robot][pair]:
            self._params[robot][pair][param] = value
        
    def set_param(self, robot, pair, param, value):
        if robot in self._params and pair in self._params[robot] and param in self._params[robot][pair]:
            self._params[robot][pair][param] = value
        else:
            raise Exception('set_param: param %s not found!' % param)
        
    def get_param(self, robot, pair, param):
        if robot in self._params and pair in self._params[robot] and param in self._params[robot][pair]:
            return self._params[robot][pair][param]
        else:
            raise Exception('get_param: param %s not found!' % param)
    
    # return suspend mode
    def check_suspend(self, robot, pair):
        if self._force_mode:
            return FORCE_SALE_MODE
        else:
            return NORMAL_MODE
    
    def set_suspend(self, robot, pair, mode):
        return None
    
    def get_balance(self, cur):
        return self._funds[cur]
    
    # return None if error
    def get_open_orders(self, pair):
        res = []
        for r in self._open_orders:
            if r['pair']==pair:
                res += [r]
         
        return res
    
    def get_open_deals_cnt(self, robot):
        return self._trade_cnt
    
    ##############################################################################################################################
    
    def place_order(self, order_type, pair, quantity, rate, limit=0.0):
        id = self._current_order_id
        self._open_orders += [{'Id': id, 'Quantity': quantity, 'pair': pair, 'open_utime': self._utime, 'close_utime': None,\
                               'QuantityRemaining': quantity, 'Type': order_type, 'Status': 'Open', 'Price': None, 'Limit': limit, 'Rate': rate}]
        if limit==0.0:
            self.process_orders()
            if not self.get_order(id):
                return None
        self._current_order_id += 1
        return id
        
    def place_order_buy(self, pair, quantity, buy_rate, limit=0.0):
        self._trade_cnt += 1
        if self._trade_cnt>self._max_trade_cnt:
            self._max_trade_cnt = self._trade_cnt
        return self.place_order('BUY', pair, quantity, buy_rate, limit)
        
    def place_order_sell(self, pair, quantity, sell_rate, limit=0.0):
        self._trade_cnt -= 1
        return self.place_order('SELL', pair, quantity, sell_rate, limit)
    
    def get_order(self, id):
        for r in self._open_orders:
            if r['Id']==id:
                return r
            
        for r in self._closed_orders:
            if r['Id']==id:
                return r
        return {}
            
    def cancel_order(self, id):
        for r in self._open_orders:
            if r['Id']==id:
                self._trade_cnt -= 1
                self._open_orders.remove(r)
                return True
        return False
    
    def process_orders(self):
        c = self.conn.cursor()
        try:
            for r in self._open_orders:
                cur1, cur2 = re.findall('(\w+)-(\w+)', r['pair'])[0]
                c.execute("""select avg(t.buy) buy, avg(t.sell) sell FROM (select * from tickers where pair=%s AND updated>=%s order by updated limit 2) t""", [r['pair'], self._utime])
                price = c.fetchone()
                if not price['buy'] or not price['sell']:
                    self._open_orders.remove(r)
                    continue
                
                if r['Type']=='BUY':
                    if r['Limit']>0.0:
                        if float(price['buy'])>r['Limit']*1.01:
                            continue
                        elif float(price['buy'])>r['Limit']:
                            price['buy'] = r['Limit']
                        
                    elif float(price['buy'])>1.2*r['Rate']:
                        self._open_orders.remove(r)
                        continue 
                        
                    cur1_amt = float(price['buy'])*r['Quantity']*(1.0+self._fee/100.0)
                    if cur1_amt>self._funds[cur1] or cur1_amt==0.0:
                        self._open_orders.remove(r)
                        continue 
                    self._funds[cur1] -= cur1_amt
                    self._funds[cur2] += r['Quantity']
                    r['Price'] = float(price['buy'])
                    r['Volume'] = cur1_amt
                    if cur1==BASE_CURRENCY and self._funds[cur1]<self._min_base_cur:
                        self._min_base_cur = self._funds[cur1]
                elif r['Type']=='SELL':
                    if r['Limit']>0.0:
                        if float(price['sell'])*1.01<r['Limit']:
                            continue
                        elif float(price['sell'])<r['Limit']:
                            price['sell'] = r['Limit']
                                        
                    cur1_amt = float(price['sell'])*r['Quantity']*(1.0-self._fee/100.0)
                    if r['Quantity']>self._funds[cur2] or cur1_amt==0.0:
                        self._open_orders.remove(r)
                        continue                     
                    self._funds[cur1] += cur1_amt
                    self._funds[cur2] -= r['Quantity']
                    r['Price'] = float(price['sell'])
                    r['Volume'] = cur1_amt
                
                r['close_utime'] = self._utime
                r['Status'] = 'Closed'
                r['QuantityRemaining'] = 0.0
                self._open_orders.remove(r)
                self._closed_orders.append(r)
        finally:
            c.close()

dt = datetime.datetime.now()
CURRENT_TIMESTAMP = '%.2d%.2d_%.2d%.2d%.2d' % (dt.month, dt.day, dt.hour, dt.minute, dt.second)
LOG_FILE_ERROR = os.path.join(LOG_PATH, 'errors_sim_%s.log' % CURRENT_TIMESTAMP)
LOG_FILE_DEBUG = os.path.join(LOG_PATH, 'debug_sim_%s.log' % CURRENT_TIMESTAMP)
LOG_FILE_INFO = os.path.join(LOG_PATH, 'trades_sim_%s.log' % CURRENT_TIMESTAMP)

if os.path.isfile(LOG_FILE_DEBUG): os.remove(LOG_FILE_DEBUG)
if os.path.isfile(LOG_FILE_INFO): os.remove(LOG_FILE_INFO)

logger = logging.getLogger("robot")
logger.setLevel(logging.DEBUG)  

if logger.level == logging.DEBUG:
    debug_fh = logging.FileHandler(LOG_FILE_DEBUG)
    debug_fh.setFormatter(None)
    debug_fh.setLevel(logging.DEBUG)
    logger.addHandler(debug_fh)

info_fh = logging.FileHandler(LOG_FILE_INFO)
info_fh.setFormatter(None)
info_fh.setLevel(logging.INFO)
logger.addHandler(info_fh)  

error_fh = logging.FileHandler(LOG_FILE_ERROR)
error_fh.setFormatter(None)
error_fh.setLevel(logging.ERROR)
logger.addHandler(error_fh)


sim = CPumpSimul(CSmartRobot, 'Smart') # , ['BTC-CFI', 'BTC-SAFEX', 'BTC-PTOY', 'BTC-STORJ', 'BTC-UBQ', 'BTC-ZEN', 'BTC-NBT', 'BTC-RLC', 'BTC-BLOCK', 'BTC-GEO']
#sim = CPumpSimul(CDeepRobot, 'Deep') # , ['BTC-FCT']
sim.setBalance(BASE_CURRENCY, 1.0)
print 'Start Balance BTC: %.3f' % sim.get_balance(BASE_CURRENCY)
sim.Execute(datetime.date(2017, 11, 7), datetime.date(2018, 1, 8))
print '====================================================================================='
print 'Result Balance:'
print sim.getInfo()