# -*- coding: utf-8 -*-

from bittrex_platform import Bittrex_platform
from pump_robot import CPumpRobot

platform = Bittrex_platform(CPumpRobot, 'Pump', ['BTC-VTC'])
platform.Execute()


