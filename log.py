import os
import message
import telegram
import exchange

from persistence import Trade
from apscheduler.schedulers.background import BackgroundScheduler

messager = message.Message()

class Logger():

	# Store the information in a csv file to be opened in Excel
	file_name = "log.csv"
	scheduler = None
	order_count = 0

	def __init__(self, a_file_name = "log.csv"):
		self.file_name = a_file_name
		self.scheduler = BackgroundScheduler()

	def initialize_log_file(self, a_file_name = "log.csv"):
		with open(a_file_name, 'w') as file:
			file.write("Date,Time,TradeCount,BestPerformingTrade,AverageDuration,ROI,BTCValue/USDValue(Wallet),PriceOfBTC,ErrorLogs")
			file.write("\n")

	def log(self, text, a_file_name = "log.csv"):
		if os.path.exists(a_file_name):
			pass
		else:
			self.initialize_log_file(a_file_name)
			
		with open(a_file_name, 'a') as file:
			file.write(text)
			file.write("\n")

	def auto_log(self):

		# Trade Logs
		trades = Trade.query.order_by(Trade.id).all()
		balances = exchange.get_balances()
		message = messager.get_log(trades, balances)
		self.log(message)

		# Order Logs
		order_message = messager.get_order_log()
		self.log(message, "order_log.csv")



	def start_scheduled_log(self, time=6):# -> BackgroundScheduler():
		
		if self.scheduler is None:
			self.scheduler = BackgroundScheduler()

		if not self.scheduler.running:
			self.scheduler.add_job(self.auto_log, 'interval', hours=time)
			self.scheduler.start()

		self.auto_log()		
			#return self.scheduler

	def stop_scheduled_log(self):
		if self.scheduler.running:
			self.scheduler.shutdown()