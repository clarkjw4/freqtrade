class Logger():

	# Store the information in a csv file to be opened in Excel
	file_name = "log.csv"

	with open(file_name) as file:
		file.write("column,names,delimitted,by,commas")
		file.write("\n")

	def write_to(self, text):
		with open(self.file_name) as file:
			file.write(text)
			file.write("\n")