import logging
import datetime

DB_SERVER="localhost"
DB_USER="robot"
DB_PASSWD="test"
DB_SCHEME="trading"

LOG_PATH = '\home\robot\log'

API_PUBLIC_KEY = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' 
API_SECRET_KEY = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

#logging.root.handlers = []
#logging.basicConfig(format='%(asctime)s : [module: %(module)s; line: %(lineno)d]  %(levelname)s : %(message)s', level=LOG_LEVEL , filename=LOG_FILE)

#suspend modes:

NORMAL_MODE = 'N' # - normal mode buy and sale
NO_BUY_MODE = 'Y' # - do not buy anything 
SALE_OUT_MODE = 'S' # - Sale out markets with gain>0
SALE_STOP_MODE = 'E' # - Sale out markets with gain>0 and move to no buy mode
FORCE_SALE_MODE = 'F' # - Force sale out everything and move to no buy mode
KEEP_GAIN = 'G' # - Keep currency to sale with gain at least +3%

DEVELOP_MODE = True

MAIL_DEAL_MODE = False

SMTP_FROM_ADDRESS ='email@domain.com'
SMTP_HOST = 'smtp.domain.com'
SMTP_PORT = 2525
SMTP_USER = 'email@domain.com'
SMTP_PASSWORD = 'xxxxxxxxxx'