import time
from datetime import timedelta
import logging
import arrow
import requests
from pandas import DataFrame
import talib.abstract as ta
import talib
import pandas as pd
import numpy as np
import math

pd.options.mode.chained_assignment = None  # default='warn'

class Indicator:

	# Trend
	def TREND(self, df):
		df['Trend'] = None
		df['Trend_Amount'] = None
		df['Trend_Direction'] = None

		for row in range(1, len(df)):
			if(df['close'].iloc[row] < df['open'].iloc[row]):
				df['Trend'].iloc[row] = -1
			else:
				df['Trend'].iloc[row] = 1

			df['Trend_Amount'].iloc[row] = df['close'].iloc[row] - df['open'].iloc[row]

			if df['Trend_Amount'].iloc[row] is not None:
				df['Trend_Direction'].iloc[row] = df['Trend_Amount'].iloc[row]

				if df['Trend_Direction'].iloc[row - 1] is not None:
					df['Trend_Direction'].iloc[row] += df['Trend_Direction'].iloc[row - 1]
				#if df['Trend_Amount'].iloc[row - 1] is not None:
				#    df['Trend_Direction'].iloc[row] += df['Trend_Amount'].iloc[row-1]

		return df

	# RSI
	def RSI (self, df):

		df['PositionRSI'] = None

		for row in range(len(df)):

			if (df['rsi'].iloc[row] < 20.0):
				df['PositionRSI'].iloc[row] = 1

			else:
				df['PositionRSI'].iloc[row] = -1

		return df

	# Stochcastic
	def STOK(self, df, n):
		#STOK = ((df['close'] - pd.rolling_min(df['low'], n)) /
		#(pd.rolling_max(df['high'], n) - pd.rolling_min(df['low'], n))) * 100
		STOK = ((df['close'] - df['low'].rolling(n).min()) /
		(df['high'].rolling(n).max() - df['low'].rolling(n).min())) * 100

		return STOK

	def STOD(self, df, n):
		#STOK = ((df['close'] - pd.rolling_min(df['low'], n)) /
		#(pd.rolling_max(df['high'], n) - pd.rolling_min(df['low'], n))) * 100
		STOK = self.STOCK(df, n)

		#STOD = pd.rolling_mean(STOK, 3)
		STOD = STOK.rolling(3).mean()

		return STOD

	def STOCH(self, df):

		#Create an "empty" column as placeholder for our /position signal
		df['PositionSTOCH'] = None

		for row in range(len(df)):

			if (df['K'].iloc[row] < 20.0) and (df['D'].iloc[row] < 20.0):
				df['PositionSTOCH'].iloc[row] = 1

			else:
				df['PositionSTOCH'].iloc[row] = -1

		return df


	# Working Bollinger Bands
	def BBANDS(self, k, df, n):
		#MA = pd.stats.moments.rolling_mean(df['close'],k)
		MA = df['close'].rolling(k).mean()
		#MSD = pd.stats.moments.rolling_std(df['close'],k)
		MSD = df['close'].rolling(k).std()
		df['upper'] = MA + (MSD*n)
		df['lower'] = MA - (MSD*n)

		#Create an "empty" column as placeholder for our /position signals
		df['PositionBBANDS'] = None

		#Fill our newly created position column - set to sell (-1) when the price hits the upper band, and set to buy (1) when it hits the lower band
		for row in range(len(df)):

			if (df['close'].iloc[row] > df['upper'].iloc[row]) and (df['close'].iloc[row-1] < df['upper'].iloc[row-1]):
				df['PositionBBANDS'].iloc[row] = -1

			if (df['close'].iloc[row] < df['lower'].iloc[row]) and (df['close'].iloc[row-1] > df['lower'].iloc[row-1]):
				df['PositionBBANDS'].iloc[row] = 1

		#Forward fill our position column to replace the "None" values with the correct long/short positions to represent the "holding" of our position
		#forward through time
		df['PositionBBANDS'].fillna(method='ffill',inplace=True)

		return df