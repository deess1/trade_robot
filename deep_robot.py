# -*- coding: utf-8 -*-

import datetime

from settings import *
import MySQLdb
import MySQLdb.cursors
import time
import traceback
import re

from pump_robot import CRobot 

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BTC_USE_LIMIT = 0.01
BTC_MIN_TRADE = 0.006
DYNAMIC_USE_BALANCE = True
MAX_TRADES_CNT = 100

# diapason drop to initialize    
MIN_DROP = -4.0
MAX_DROP = -4.5
# threshold to buy
DELTA_READY = -6.2
BUY_THRESHOLD = 0.8
BUY_LIMIT_PRC = 3.0
# pump parameters
MAX_PUMP_PRC = 10.0
MIN_PUMP_PRC = 3.0
SHORT_TIME_INTERVAL = 1
MAX_PRICE_CHANGE = 5.0
MIN_PRICE_CHANGE = 3.0


MIN_PUMP_EXPOSITION = 6.0
MAX_PUMP_EXPOSITION = 18.0 
# stoploss parameters    
TIMEOUT_PRC = 1.5
TIMEOUT_DAYS = 3.5
LONG_TIME_INTERVAL = 4 # hours
TIMEOUT_PRICE_CHANGE = 1.0   

    
class CDeepRobot(CRobot):
            
    def set_default_params(self):
        super(CDeepRobot, self).set_default_params()

        self.set_default_param('analyse_days', '2')  # last days of history to analyse
        self.set_default_param('buy_order_id', '')
        self.set_default_param('sell_order_id', '')
        self.set_default_param('last_buy_rate', '0.0')
        self.set_default_param('last_buy_utime', '0')
        self.set_default_param('last_deal', '0')
        self.set_default_param('init_trend', '0.0')
        self.set_default_param('deal_type', '') 
        self.set_default_param('init_price', '')
        self.set_default_param('delta_drop', '')
        self.set_default_param('drop_time', '')
        self.set_default_param('min_delta', '0.0')
        self.set_default_param('max_gain', '0.0')
        
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
        super(CDeepRobot, self).__init__(platform, pair, robot)
        if self.utime: self.execute()
    
    def execute(self):
############################################################################################################################################################################
        if self.get_param('state')=='wait':
            #self.Debug('executed in wait state')
            
            if not self.history_exists(days=5):
                #self.Debug('no necessary history exists: 5 days. exit')
                return
                    
            if self.check_suspend()!=NORMAL_MODE:
                #self.Debug('suspend mode detected: %s. exit' % self.check_suspend())
                return
            
            #if self.get_int_param('last_deal')+3600*48>self.utime:
                #self.Debug('last_deal found. exit')
            #    return
            
            if self.get_open_deals_cnt()>MAX_TRADES_CNT:
                return
            
            delta_drop = self.get_delta(minutes=15)
            
            #self.Debug('delta_drop=%.2f, trend=%.2f' % (delta_drop, trend))
            
            if delta_drop<-4.0:
                init_price = float(self.get_max_buy_price(hours=2))
                if init_price>1.15*self._curr_buy_rate:
                    init_price = 1.15*self._curr_buy_rate
                    
                self.set_param('init_price', init_price )
                self.set_param('drop_time', self.utime-900)
                self.set_param('min_delta', '100.0')
                self.set_param('state', 'ready')
                self.Debug('change state -> ready')
                
                #if DEVELOP_MODE:
                #    self.set_param('param1', trend)
                

############################################################################################################################################################################        
        elif self.get_param('state')=='ready':
            if self.get_open_deals_cnt()>MAX_TRADES_CNT:
                self.set_param('state', 'wait')
                return
            
            a1 = self.get_1hour_avg(minutes=0)
            a2 = self.get_1hour_avg(hours=2)
            a3 = self.get_1hour_avg(hours=4) 
            if a1<=0.0 or a2<=0.0 or a3<=0.0:
                return
            trend1 = 100.0*(a2-a1)/a1
            trend2 = 100.0*(a3-a1)/a1
            
            delta_prc = 100.0*(self._curr_buy_rate-float(self.get_param('init_price')))/float(self.get_param('init_price'))
            min_delta = float(self.get_param('min_delta'))
            if delta_prc<min_delta:
                min_delta = delta_prc
                self.set_param('min_delta', min_delta)
            self.Debug('init_price=%.8f, min_delta=%.2f, delta_prc=%.2f, trend=%.2f' % (float(self.get_param('init_price')), float(self.get_param('min_delta')), delta_prc, trend1))
            
            if delta_prc<-20.0 and delta_prc<0.95*min_delta and abs(trend1)<0.8 and abs(trend2)<0.8:
                
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
                
                volume_to_buy = round(btc_balance/self._curr_buy_rate)
                self.Info('Try to buy: %f for %.8f' % (volume_to_buy, self._curr_buy_rate))
                
                #id = self._platform.place_order_buy(self._pair, volume_to_buy, self._curr_buy_rate, self._curr_buy_rate*BUY_LIMIT_PRC)
                id = self._platform.place_order_buy(self._pair, volume_to_buy, self._curr_buy_rate)
                if id:
                    msg = 'Place order to buy %f for %f BTC  (buy rate %.8f)' % (volume_to_buy, btc_balance, self._curr_buy_rate)
                    self.Info(msg) 
                    self.set_param('state', 'buying')
                    self.set_param('buy_order_id',id)
                    self.Debug('change state -> buying')
                    
                    if DEVELOP_MODE:
                        self.set_param('param1', delta_prc)
                        self.set_param('param2', trend1)
                        self.set_param('param3', trend2)
                        #self.set_param('param2', self.get_param('delta_drop'))
                
                
                self.Debug('Passed. start to buy')
                self.Info('Buy for %.8f' % self._curr_buy_rate)
                self.set_param('state', 'pump')
                self.set_param('last_buy_rate', self._curr_buy_rate)
                self.set_param('last_buy_utime', self.utime)
                
            elif delta_prc>-5.0:
                self.set_param('state', 'wait')
                self.Debug('Drop not found. change state -> wait')         
                
            elif self.utime-self.get_int_param('drop_time')>2*24*3600:
                self.set_param('state', 'wait')
                self.Debug('Deep not reached. change state -> wait')         
        
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
                    if self.utime-opened_time>1800:
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
                self.set_param('max_gain', '-100.0')
                
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
                
            suspend_mode = self.check_suspend()
            
            max_gain = float(self.get_param('max_gain'))
            if gain_prc>max_gain:
                max_gain = gain_prc
                self.set_param('max_gain', max_gain)
                
            to_sell = False
             
            if gain_prc>0.0 and suspend_mode in (SALE_OUT_MODE, SALE_STOP_MODE):
                deal_type = 'Sale out'
                to_sell = True
            elif suspend_mode==FORCE_SALE_MODE:
                deal_type = 'Force sale'
                to_sell = True
            elif gain_prc>MIN_PUMP_PRC and delta_prc<=0.0 and suspend_mode==KEEP_GAIN:
                deal_type = 'Keep gain'
                to_sell = True
            elif (gain_prc>100.0) or (gain_prc>80.0 and delta_prc<=0.0) or (gain_prc>50.0 and delta_prc<=-5.0):
                deal_type = 'TakePump'
                to_sell = True
            elif (gain_prc>20.0) and gain_prc<0.9*max_gain and delta_prc<-1.0:
                deal_type = 'MidGain'
                to_sell = True
            elif (gain_prc<-20.0) and exposition>48.0 and delta_prc<-1.0:
                deal_type = 'StopLoss'
                to_sell = True
            elif exposition>24*TIMEOUT_DAYS and delta_prc<-0.5 and last_trend<0.0:
                deal_type = 'TimeOut'
                to_sell = True

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
