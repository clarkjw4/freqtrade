class Logger():

	# Store the information in a csv file to be opened in Excel
	file_name = "log.csv"

	def init(self):
		with open(file_name) as file:
			file.write("Time,TradeCount,BestPerformingTrade,AverageDuration,ROI,"
						+ "BTCValue(Wallet),USDValue(Wallet),PriceOfBTC,ErrorLogs")
			file.write("\n")

	def log(self, text):
		try:
			with open(self.file_name) as file:
				file.write(text)
				file.write("\n")
		except IOError as e:
			init()
			file.write(text)
			file.write("\n")
		