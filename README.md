# trade_robot

This is an example of universal system written in python to run various types of trading robots on different crypto exchange platforms.

<p><i>start_robot.py</i> - main script running as a cronjob 24/7 each check interval
<p><i>settings.py</i> - settings with credentials to connect to exchange, to database and so on 
<p><i>load_tickers.py</i> - script to request bunch of tickers from exchange platform running as independed cronjob. Fills tickers table 
<p><i>bittrex.py</i> - Public trade API for bittrex crypto-exchange
<p><i>bittrex_platform.py</i> - Wrapper for bittrex API providing work enviroment for CRobot class
<p><i>pump_robot.py</i> - Base CRobot class of trading robot. Robot looks for pairs with signs of pamp and trade them. Send mail for completed trades and statistic
<p><i>deep_robot.py</i> - Another type of CRobot
<p><i>simulator.py</i> - Simulator to run CRobots on historical set of tickers and adjust robot's parameters
<p><i>*.sql</i> - database tables for MySQL 

