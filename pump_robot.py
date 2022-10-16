# -*- coding: utf-8 -*-

import datetime

from settings import *
import MySQLdb
import MySQLdb.cursors
import time
import traceback
import re

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BTC_USE_LIMIT = 0.01
BTC_MIN_TRADE = 0.006
DYNAMIC_USE_BALANCE = True
MAX_TRADES_CNT = 35

# diapason drop to initialize    
MIN_DROP = -4.0
MAX_DROP = -4.5
# threshold to buy
DELTA_READY = -6.2
BUY_THRESHOLD = 0.8
BUY_LIMIT_PRC = 3.0
# pump parameters
MAX_PUMP_PRC = 5.0
MIN_PUMP_PRC = 3.0
SHORT_TIME_INTERVAL = 1
MAX_PRICE_CHANGE = 5.0
MIN_PRICE_CHANGE = 3.0

CHECK_DROP_ACTIVITY = False
DROP_MORATORIUM = 6.0 #hours

MIN_PUMP_EXPOSITION = 6.0
MAX_PUMP_EXPOSITION = 18.0 
# stoploss parameters    
TIMEOUT_PRC = 1.5
TIMEOUT_DAYS = 3.5
LONG_TIME_INTERVAL = 4 # hours
TIMEOUT_PRICE_CHANGE = 1.0   

class CRobot(object):
    conn = None
    _pair = None
    _robot = None   # robot name
    _platform = None
    utime = None  # current time if robot processed (exist ticker and time interval passed)
    
    def Debug(self, message):
        self._platform.debug('{%s:%s} %s' % (self._robot, self._pair, message))

    def Info(self, message):
        self._platform.info('{%s:%s} %s' % (self._robot, self._pair, message))
     
    def Error(self, message):
        self._platform.error('{%s:%s} %s' % (self._robot, self._pair, message))
    
    def send_mail(self, subject, message): 
        try:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            server.login(SMTP_USER, SMTP_PASSWORD)
            msg = MIMEMultipart('alternative')
            msg.set_charset('utf-8')
            msg['Subject'] = subject
            msg['From'] = SMTP_FROM_ADDRESS
            msg['To'] = 'receiver@domain.ru'
            msg.attach(MIMEText(message, 'text', 'utf-8'))
            
            server.sendmail(SMTP_FROM_ADDRESS, 'receiver@domain.ru', msg.as_string())
            server.quit()
        except:
            None  
            
    def set_default_param(self, param, value):
        self._platform.set_default_param(self._robot, self._pair, param, value)
    
    def set_param(self, param, value):
        self._platform.set_param(self._robot, self._pair, param, value)
    
    def get_param(self, param):
        return self._platform.get_param(self._robot, self._pair, param)

    def get_int_param(self, param):
        return int(self._platform.get_param(self._robot, self._pair, param))

    def set_default_params(self):
        self.set_default_param('state', 'wait')
        self.set_default_param('last_run', '0')
        self.set_default_param('interval', '300') # = 5 min        
        self.set_default_param('check_period', '280') # < 5 min
        
    def load_params(self):
        self._platform.load_params(self._robot, self._pair)
        self.set_default_params()
     
    # return suspend mode
    def check_suspend(self):
        return self._platform.check_suspend(self._robot, self._pair)
    
    def set_suspend(self, mode):
        self._platform.set_suspend(self._robot, self._pair, mode)

    def get_open_deals_cnt(self):
        return self._platform.get_open_deals_cnt(self._robot)
            
    def load_ticker(self):
        #self.Debug('load_ticker')
        if self._platform.get_utime()-self.get_int_param('last_run')<120:
            #self.Debug('Last run: %d, Current Timestamp: %d. Period not reached. exit' % (self.get_int_param('last_run'), cur_time))
            return

        c = self.conn.cursor()
        try:
            c.execute("""select * FROM tickers where pair=%s AND updated between %s and %s order by updated desc limit 1""", [self._pair, self._platform.get_utime()-300, self._platform.get_utime()+10])

            ticker = c.fetchone()
            if not ticker: return
            if self.get_int_param('last_run')==int(ticker['updated']): return
    
            self._curr_buy_rate = float(ticker['buy'])
            self._curr_sell_rate = float(ticker['sell'])

            self.utime = int(ticker['updated'])
            self.set_param('last_run', self.utime)
        finally:
            c.close()
        
    def history_exists(self, **time_delta):
        delta = datetime.timedelta(**time_delta).total_seconds()
        c = self.conn.cursor()
        try:
            c.execute("""SELECT COUNT(*) c FROM tickers WHERE pair=%s AND updated BETWEEN %s AND %s""", [self._pair, self.utime-delta, self.utime])
            row = c.fetchone()
            if row:
                if row['c']/float(delta/self.get_int_param('interval'))>0.8:
                    return True
            return False
        finally:
            c.close()
    
    def get_delta(self, **time_delta):
        delta = datetime.timedelta(**time_delta).total_seconds()
        c = self.conn.cursor()
        try:
            c.execute("""SELECT buy FROM tickers WHERE pair=%s AND updated>%s ORDER BY updated LIMIT 1""", [self._pair, self.utime-delta-50])
            row = c.fetchone()
            if row and row['buy']:
                return 100.0*(self._curr_buy_rate-float(row['buy']))/float(row['buy'])
            return -99.9
        finally:
            c.close()
            
    def get_delta2(self, utime):
        c = self.conn.cursor()
        try:
            c.execute("""SELECT buy FROM tickers WHERE pair=%s AND updated>=%s ORDER BY updated LIMIT 1""", [self._pair, utime])
            row = c.fetchone()
            if row and row['buy']:
                return 100.0*(self._curr_buy_rate-float(row['buy']))/float(row['buy'])
            return -99.9
        finally:
            c.close()            
    
    def get_1hour_avg(self, **time_delta):
        delta = datetime.timedelta(**time_delta).total_seconds()
        c = self.conn.cursor()
        try:
            c.execute("""SELECT avg(buy) buy FROM tickers WHERE pair=%s AND updated between %s AND %s""", [self._pair, self.utime-delta-3600, self.utime-delta])
            row = c.fetchone()
            if row and row['buy']:
                return float(row['buy'])
            return 0.0
        finally:
            c.close()
            
    def get_max_buy_price(self, **time_delta):
        delta = datetime.timedelta(**time_delta).total_seconds()
        c = self.conn.cursor()
        try:
            c.execute("""SELECT max(buy) buy FROM tickers WHERE pair=%s AND updated between %s AND %s""", [self._pair, self.utime-delta, self.utime-300])
            row = c.fetchone()
            if row and row['buy']:
                return float(row['buy'])
            return 0.0
        finally:
            c.close()
    
    def get_last_avg_buy(self, **time_delta):
        delta = datetime.timedelta(**time_delta).total_seconds()
        c = self.conn.cursor()
        try:
            c.execute("""SELECT avg(buy) buy FROM tickers WHERE pair=%s AND updated between %s AND %s""", [self._pair, self.utime-delta, self.utime-60*3600])
            row = c.fetchone()
            if row and row['buy']:
                return float(row['buy'])
            return 0.0
        finally:
            c.close()
            
    def check_drop_activity(self):
        delta = datetime.timedelta(hours=2).total_seconds()
        c = self.conn.cursor()
        try:
            c.execute("""SELECT count(pair) c FROM drop_activity WHERE updated between %s AND %s""", [self.utime-delta, self.utime])
            row = c.fetchone()
            curr_val = int(row['c'])
            c.execute("""SELECT count(pair) c FROM drop_activity WHERE updated between %s AND %s""", [self.utime-2*delta, self.utime-delta])
            row = c.fetchone()
            prev_val = int(row['c'])
            if prev_val>30:
                return float(curr_val)/float(prev_val)>4.0 
            else:
                return False
        finally:
            c.close()            
    
    def __init__(self, platform, pair, robot):
        self._pair = pair        
        self._robot = robot
        self._platform = platform
        self.conn = self._platform.conn
        self.utime = None
        self.load_params()
        self.load_ticker()
    
                 
#############################################################################################################
#############################################################################################################
    
class CSmartRobot(CRobot):
            
    def set_default_params(self):
        super(CSmartRobot, self).set_default_params()

        self.set_default_param('analyse_days', '2')  # last days of history to analyse
        self.set_default_param('buy_order_id', '')
        self.set_default_param('sell_order_id', '')
        self.set_default_param('last_buy_rate', '0.0')
        self.set_default_param('last_buy_utime', '0')
        self.set_default_param('last_deal', '0')
        self.set_default_param('init_trend', '0.0')
        self.set_default_param('deal_type', '') 
        self.set_default_param('init_drop', '')
        self.set_default_param('delta_drop', '')
        self.set_default_param('drop_time', '')
        self.set_default_param('drop_activity', '0')
        
        if DEVELOP_MODE:
            self.set_default_param('param1', '0.0') 
            self.set_default_param('param2', '0.0')
            self.set_default_param('param3', '0.0')
            self.set_default_param('param4', '0.0')
            self.set_default_param('param5', '0.0')
            self.set_default_param('param6', '0.0')
            self.set_default_param('param7', '0.0')
            self.set_default_param('param8', '0.0')
            self.set_default_param('param9', '0.0')

    def __init__(self, platform, pair, robot):
        super(CSmartRobot, self).__init__(platform, pair, robot)
        if self.utime: self.execute()
    
    def execute(self):
############################################################################################################################################################################
        delta_drop = self.get_delta(minutes=15)
        if CHECK_DROP_ACTIVITY and delta_drop<MIN_DROP:
            try:
                c = self.conn.cursor()
                c.execute("""INSERT INTO drop_activity(pair, updated, drop_time, delta_drop)\
                VALUES(%s, %s, %s, %s)""", [self._pair, self.utime, datetime.datetime.fromtimestamp(self.utime), delta_drop])
            except:
                None
            finally:
                c.close()        
                
        if self.get_param('state')=='wait':
            #self.Debug('executed in wait state')
            
            if not self.history_exists(days=5):
                #self.Debug('no necessary history exists: 5 days. exit')
                return
                    
            if self.check_suspend()!=NORMAL_MODE:
                #self.Debug('suspend mode detected: %s. exit' % self.check_suspend())
                return
            
            if self.get_int_param('last_deal')+3600*48>self.utime:
                #self.Debug('last_deal found. exit')
                return
            
            if self.get_open_deals_cnt()>MAX_TRADES_CNT:
                return
            
            a2 = self.get_1hour_avg(minutes=15)
            a1 = self.get_1hour_avg(days=3)
            if a1<=0.0 or a2<=0.0:
                return
            trend = 100.0*(a2-a1)/a1       
            #delta_drop = self.get_delta(minutes=15)
            
            #self.Debug('delta_drop=%.2f, trend=%.2f' % (delta_drop, trend))
            
            if delta_drop<MIN_DROP and delta_drop>MAX_DROP and trend>-20.0 and trend<140.0:
                self.set_param('init_drop', delta_drop)
                self.set_param('drop_time', self.utime-900)
                self.set_param('init_trend', trend)
                self.set_param('state', 'ready')
                self.Debug('change state -> ready')
                
                #if DEVELOP_MODE:
                #    self.set_param('param1', trend)
                

############################################################################################################################################################################        
        elif self.get_param('state')=='ready':
            if self.get_open_deals_cnt()>MAX_TRADES_CNT:
                self.set_param('state', 'wait')
                return
            
            delta_prc = self.get_delta(minutes=10)
            if delta_prc>DELTA_READY:
                delta_drop = self.get_delta2(self.get_int_param('drop_time'))
                last_avg = self.get_last_avg_buy(days=5)
                min_delta = 100.0*(last_avg-self._curr_buy_rate)/self._curr_buy_rate
                trend = self.get_param('init_trend') 
                
                if CHECK_DROP_ACTIVITY:
                    if self.get_int_param('drop_activity')>self.utime-3600*DROP_MORATORIUM:
                        self.Debug('Skip drop moratorium. state -> wait')
                        self.set_param('state', 'wait')
                        return
                    elif self.check_drop_activity():
                        self.Debug('Skip drop moratorium. set utime, state -> wait')
                        self.set_param('drop_activity', self.utime)
                        self.set_param('state', 'wait')
                        return
                
                #if delta_drop-float(self.get_param('init_drop'))<BUY_THRESHOLD and min_delta>-40.0:# and (min_delta>0.6 or (min_delta<0.6 and trend<3.5 and 3.5*trend<min_delta)):
                if delta_drop-float(self.get_param('init_drop'))<BUY_THRESHOLD and min_delta>-40.0:
                    self.Debug('conditions passed. start to buy')
                    balance = self._platform.get_balance('BTC')
                    if not balance:
                        self.set_param('state', 'wait')
                        self.Debug('No balance. change state -> wait')
                        return
                    
                    self.Debug('balance queried: %f BTC' % balance)
                    
                    if DYNAMIC_USE_BALANCE:
                        if balance>BTC_MIN_TRADE:
                            btc_balance = min(0.95*balance/3, BTC_USE_LIMIT)
                            if btc_balance<BTC_MIN_TRADE:
                                btc_balance=BTC_MIN_TRADE
                        else:
                            btc_balance = 0.0
                    else:
                        btc_balance = min(0.95*balance, BTC_USE_LIMIT)
                        
                    if btc_balance<BTC_MIN_TRADE:
                        self.set_param('state', 'wait')                        
                        self.Debug('balance not enougth. change state -> wait')
                        return
                    
                    volume_to_buy = round(btc_balance/self._curr_buy_rate, 2)
                    self.Info('Try to buy: %f for %.8f' % (volume_to_buy, self._curr_buy_rate))
                    #buy_limit_prc = BUY_LIMIT_PRC - BUY_LIMIT_PRC*(float(self.get_param('init_drop'))-MIN_DROP)/(MAX_DROP-MIN_DROP)
                    buy_limit_prc = 5.0
                    
                    #id = self._platform.place_order_buy(self._pair, volume_to_buy, self._curr_buy_rate, self._curr_buy_rate*BUY_LIMIT_PRC)
                    id = self._platform.place_order_buy(self._pair, volume_to_buy, self._curr_buy_rate, self._curr_buy_rate*(1-0.01*buy_limit_prc))
                    if id:
                        msg = 'Place order to buy %f for %f BTC  (buy rate %.8f)' % (volume_to_buy, btc_balance, self._curr_buy_rate)
                        self.Info(msg) 
                        self.set_param('state', 'buying')
                        self.set_param('buy_order_id',id)
                        self.Debug('change state -> buying')
                        
                        if DEVELOP_MODE:
                            self.set_param('param1', min_delta)
                            self.set_param('param2', trend)
                            #self.set_param('param2', self.get_param('delta_drop'))
                    else:
                        self.set_param('state', 'wait')
                        self.Info('error create buy order. change state -> wait')
    
                else:
                    self.set_param('state', 'wait')
                    self.Debug('change state -> wait')

            elif self.utime-self.get_int_param('drop_time')>900:
                self.set_param('state', 'wait')
                self.Debug('Init drop not passed. change state -> wait')            
        
############################################################################################################################################################################                
        elif self.get_param('state')=='buying':
            self.Debug('executed in buying state')
            open_orders = self._platform.get_open_orders(self._pair)
            if open_orders==None:
                return

            opened_time = None 
            for order in open_orders:
                if order['Id']==self.get_param('buy_order_id'):
                    self.Debug('found open order: %s' % self.get_param('buy_order_id'))
                    opened_time = order['open_utime']
                    if self.utime-opened_time>6*3600:
                        if order['Quantity']>order['QuantityRemaining']:
                            if not self._platform.cancel_order(order['Id']):
                                self.Error('Error cancel order')
                            opened_time = None
                            self.Info('Order was filled partly %.8f from %.8f. Go to pump mode' % (order['Quantity']-order['QuantityRemaining'], order['Quantity']))
                        
                        elif self._platform.cancel_order(order['Id']):
                            self.set_param('state', 'wait')
                            self.Info('Ticket was not bought in time. Cancel order')
                            self.Debug('unsuccessful buy, cancel order. change state -> wait')
                            return
                    break
            
            if not opened_time:
                order = self._platform.get_order(self.get_param('buy_order_id'))
                if order==None: return
                elif order=={}:
                    self.set_param('state', 'wait')
                    self.Debug('unsuccessful buy, order was canceled by platform. change state -> wait')
                    return
                
                self.set_param('last_buy_rate', order['Price'])
                self.set_param('last_buy_utime', order['close_utime'])
                self.set_param('state', 'pump')
                self.Debug('change state -> pump')
                self.execute()
                return            
        
        elif self.get_param('state')=='pump':      
            #self.Debug('executed in pump state')
            
            try:
                last_buy_rate = float(self.get_param('last_buy_rate'))
                last_buy_utime = self.get_int_param('last_buy_utime')
            except:
                self.Error('Error get last_buy_rate, last_buy_utime!!!!')
                self.set_param('state', 'wait')
                return
            if last_buy_rate==0.0:
                self.Error('Error get last_buy_rate=0.0!!!!')
                self.set_param('state', 'wait')
                return
            
            delta_prc = self.get_delta(minutes=SHORT_TIME_INTERVAL*5+1)
            gain_prc = 100.0*(self._curr_sell_rate-last_buy_rate)/last_buy_rate-self._platform._fee
            exposition = (self.utime-last_buy_utime)/3600.0
            a2 = self.get_1hour_avg(minutes=0)
            a1 = self.get_1hour_avg(hours=LONG_TIME_INTERVAL)
            if a1>0.0 and a2>0.0:
                last_trend = 100.0*(a2-a1)/a1
            else:
                last_trend = 0.0

            drop_activity = False
            drop_activity_str =''
            if CHECK_DROP_ACTIVITY:
                if self.get_int_param('drop_activity')>self.utime-3600*exposition:
                    drop_activity = True
                    drop_activity_str = '.DA'
                elif self.check_drop_activity():
                    self.Debug('Set drop_activity in pump mode')
                    self.set_param('drop_activity', self.utime)
                    drop_activity = True
                    drop_activity_str = '.DA'
            else:
                drop_activity = True
                        
            self.Debug('last delta price: %.2f%%, gain: %.2f%%, trend: %.2f%%, exposition: %.2f %s' % (delta_prc, gain_prc, last_trend, exposition, drop_activity_str))
             
            to_sell = False
            deal_type = ''
            trades_cnt = self.get_open_deals_cnt()
               
            suspend_mode = self.check_suspend()
            
            if gain_prc>0.0 and suspend_mode in (SALE_OUT_MODE, SALE_STOP_MODE):
                deal_type = 'Sale out'
                to_sell = True
            elif suspend_mode==FORCE_SALE_MODE:
                deal_type = 'Force sale'
                to_sell = True
            elif gain_prc>MIN_PUMP_PRC and delta_prc<=0.0 and suspend_mode==KEEP_GAIN:
                deal_type = 'Keep gain'
                to_sell = True
            
            elif (gain_prc>25.0) or (gain_prc>3.0 and delta_prc<-0.3):
                deal_type = 'MaxGain'
                to_sell = True
            elif gain_prc<-5.0:
                deal_type = 'StopLoss'
                to_sell = True
            #===================================================================
            # elif gain_prc>MIN_PUMP_PRC and (delta_prc<MAX_PRICE_CHANGE or last_trend<0.0) and exposition>MIN_PUMP_EXPOSITION and exposition<MAX_PUMP_EXPOSITION:
            #     deal_type = 'MinGain'
            #     to_sell = True
            # elif ((gain_prc>TIMEOUT_PRC) or (gain_prc<-8.0 and gain_prc>-18.0 and trades_cnt>MAX_TRADES_CNT-2 and drop_activity)) and last_trend<TIMEOUT_PRICE_CHANGE and delta_prc<MAX_PRICE_CHANGE and exposition>MAX_PUMP_EXPOSITION and exposition<=24*TIMEOUT_DAYS and suspend_mode!=KEEP_GAIN:
            #     deal_type = 'Timeout'
            #     if CHECK_DROP_ACTIVITY and drop_activity:
            #         deal_type += '.DA'
            #          
            #     to_sell = True
            # elif trades_cnt>MAX_TRADES_CNT-2 and gain_prc>-30.0 and last_trend<5.0 and exposition>24*TIMEOUT_DAYS and suspend_mode!=KEEP_GAIN:
            #     deal_type = 'StopLoss.Busy'
            #     to_sell = True
            # elif trades_cnt<=MAX_TRADES_CNT-2 and gain_prc>-8.0 and last_trend<0.0  and exposition>24*TIMEOUT_DAYS and suspend_mode!=KEEP_GAIN:
            #     deal_type = 'StopLoss.Free'
            #     to_sell = True
            #===================================================================
                
            if to_sell:
                cur1, cur2 = re.findall('(\w+)-(\w+)', self._pair)[0]
                balance = self._platform.get_balance(cur2) 
                if balance==None: return
                if balance==0.0:
                    if self.check_suspend()==NORMAL_MODE:
                        self.set_param('state', 'wait')
                        self.Debug('change state -> wait')
                    self.Error('Balance %s is empty! change state -> wait' % cur2)
                    self.set_param('state', 'wait')
                    return
                id = self._platform.place_order_sell(self._pair, balance, self._curr_sell_rate)
                if id:
                    msg = 'Place order to sell [%s] with rate %.8f  (last buy rate was %.8f). Expected gain is %.2f%%' % (deal_type, self._curr_sell_rate, last_buy_rate, gain_prc)
                    self.Info(msg) 
                    #self.send_mail('sell %s' % self._pair, msg)
                    self.set_param('sell_order_id',id)
                    self.set_param('state', 'selling')
                    self.set_param('deal_type', deal_type)
                    self.Debug('change state -> selling')
                    
                    #if DEVELOP_MODE:
                    #    self.set_param('param2', last_trend)
                    
             
        elif self.get_param('state')=='selling':
            self.Debug('executed in selling state')
            open_orders = self._platform.get_open_orders(self._pair)
            if open_orders==None:
                return

            opened_time = None 
            for order in open_orders:
                if order['Id']==self.get_param('sell_order_id'):
                    self.Debug('found open order: %s' % self.get_param('sell_order_id'))
                    opened_time = order['open_utime']
            
            if not opened_time:
                buy_order = self._platform.get_order(self.get_param('buy_order_id'))
                sell_order = self._platform.get_order(self.get_param('sell_order_id'))
                gain_prc = 100.0*(sell_order['Price']-buy_order['Price'])/buy_order['Price'] - self._platform._fee
                exposition = float(sell_order['close_utime']-buy_order['close_utime'])/3600.0
                msg = '%s: Deal [%s] is completed. Real gain is %.2f%%, exposition: %.2f hour.' % (self._pair, self.get_param('deal_type'), gain_prc, exposition)
                self.Info(msg)
                self.set_param('last_deal', self.utime)

                if MAIL_DEAL_MODE:
                    self.send_mail('buy %s' % self._pair, msg)
                
                c = self.conn.cursor()
                try:
                    c.execute("""INSERT INTO pump_deals(robot, pair, volume, buy_utime, sell_utime, buy_time, sell_time, buy_price, sell_price, deal_type, exposition, gain)\
                    VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", [self._robot, self._pair, buy_order['Volume'], buy_order['close_utime'], sell_order['close_utime'], datetime.datetime.fromtimestamp(buy_order['close_utime']), datetime.datetime.fromtimestamp(sell_order['close_utime']), buy_order['Price'], sell_order['Price'], self.get_param('deal_type'), exposition, gain_prc ])
                    
                    if DEVELOP_MODE:
                        c.execute("""UPDATE pump_deals SET param1=%s, param2=%s, param3=%s, param4=%s, param5=%s, param6=%s, param7=%s, param8=%s, param9=%s\
                        WHERE robot=%s AND pair=%s AND buy_utime=%s""",
                        [self.get_param('param1'), self.get_param('param2'), self.get_param('param3'), self.get_param('param4'), self.get_param('param5'), self.get_param('param6'), self.get_param('param7'), self.get_param('param8'), self.get_param('param9'),
                        self._robot, self._pair, buy_order['close_utime']])
                        
                        self.set_param('param1','0.0')    
                        self.set_param('param2','0.0')
                        self.set_param('param3','0.0')
                        self.set_param('param4','0.0')
                        self.set_param('param5','0.0')
                        self.set_param('param6','0.0')
                        self.set_param('param7','0.0')
                        self.set_param('param8','0.0')
                        self.set_param('param9','0.0')
                        
                finally:
                    c.close()
                
                suspend_mode = self.check_suspend() 
                if suspend_mode in (SALE_STOP_MODE, FORCE_SALE_MODE):
                    self.set_param('state', 'stop')
                    self.Debug('change state -> stop')
                else:
                    self.set_param('state', 'wait')
                    self.Debug('change state -> wait')
                    if suspend_mode!=NORMAL_MODE:
                        self.set_suspend(NORMAL_MODE)
                    
                self.set_param('last_buy_rate', '0.0')
                self.set_param('buy_order_id', '')
                self.set_param('sell_order_id','')
                #self.set_param('deal_type','')
                self.execute()
                return            
            
        elif self.get_param('state')=='stop':
            if self.check_suspend()==NORMAL_MODE:
                self.set_param('state', 'wait')
                self.Debug('change state -> wait')
            return
        else:
            self.Error('wrong state: %s' % self.get_param('state'))
