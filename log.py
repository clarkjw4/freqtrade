import os

class Logger():

	# Store the information in a csv file to be opened in Excel
	file_name = "log.csv"

	def init(self):
		file = open(self.file_name, 'w')
		file.write("Date,Time,TradeCount,BestPerformingTrade,AverageDuration,ROI,BTCValue/USDValue(Wallet),PriceOfBTC,ErrorLogs")
		file.write("\n")
		file.close ()

	def log(self, text):
		if os.path.exists(self.file_name):
			pass

		else:
			self.init()
			
		with open(self.file_name, 'a') as file:
			file.write(text)
			file.write("\n")