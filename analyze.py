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

import indicator


logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

indicators = indicator.Indicator()

# Backtesting Counter
class Counter:
    counter = 0

def get_ticker(pair: str, minimum_date: arrow.Arrow) -> dict:
    """
    Request ticker data from Bittrex for a given currency pair
    """
    url = 'https://bittrex.com/Api/v2.0/pub/market/GetTicks'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
    }
    params = {
        'marketName': pair.replace('_', '-'),
        'tickInterval': 'fiveMin',
        '_': minimum_date.timestamp * 1000
    }
    
    response = requests.get(url, params=params, headers=headers)

    try:

        #print(response)

        while (response.status_code != requests.codes.ok):
            response = requests.get(url, params=params, headers=headers)
            logger.debug("{0}: Retry establishing connection to Bittrex.".format(response))
            time.sleep(25)

        data = response.json()

        if not data['success']:
            raise RuntimeError('BITTREX: {}'.format(data['message']))
        return data
    
    except:
        logger.debug(response)
        raise RuntimeError("{0}: TimeOut Occurred".format(response))

def get_btc_current_price():
    # returns the current btc price in USD
    url = "https://api.coindesk.com/v1/bpi/currentprice.json"
    
    data = requests.get(url).json()

    return data['bpi']['USD']['rate_float']


def parse_ticker_dataframe(ticker: list, minimum_date: arrow.Arrow) -> DataFrame:
    """
    Analyses the trend for the given pair
    :param pair: pair as str in format BTC_ETH or BTC-ETH
    :return: DataFrame
    """
    df = DataFrame(ticker) \
        .drop('BV', 1) \
        .rename(columns={'C':'close', 'V':'volume', 'O':'open', 'H':'high', 'L':'low', 'T':'date'}) \
        .sort_values('date')
    return df[df['date'].map(arrow.get) > minimum_date]


def populate_indicators(dataframe: DataFrame) -> DataFrame:
    """
    Adds several different TA indicators to the given DataFrame
    """

    # Log the dataframe
    dataframe.to_csv("dataframe.csv", sep='\t')

    #Determine Trend
    dataframe = indicators.TREND(dataframe)

    #Exponential Moving Average
    dataframe['ema'] = ta.EMA(dataframe, timeperiod=33)

    #Parabolic SAR
    dataframe['sar'] = ta.SAR(dataframe, 0.02, 0.22)

    #Average Directional Movement Index
    dataframe['adx'] = ta.ADX(dataframe)

    #MACD
    macd = ta.MACD(dataframe)
    dataframe['macd'] = macd['macd']
    dataframe['macds'] = macd['macdsignal']
    dataframe['macdh'] = macd['macdhist']

    #Relative Strength Index
    dataframe['rsi'] = ta.RSI(dataframe, 14)
    dataframe = indicators.RSI (dataframe)

    #Absolute Price Oscillator
    dataframe['apo'] = ta.APO(dataframe, fastperiod=12, slowperiod=26, matype=0)

    #Momentum
    dataframe['mom'] = ta.MOM(dataframe, 10)

    #Bollinger Bands
    dataframe = indicators.BBANDS(20, dataframe, 2)

    # Stochcastic
    dataframe['K'] = indicators.STOK(dataframe, 14)
    dataframe['D'] = indicators.STOD(dataframe, 14)
    dataframe = indicators.STOCH (dataframe)

    # if Counter.counter < 30:
    #     print(dataframe)
    #     print (macd)
    #     print (dataframe ['adx'])
    #     Counter.counter = Counter.counter + 1
    
    # else:
    #     exit()
    
    return dataframe

def populate_buy_trend(dataframe: DataFrame) -> DataFrame:
    """
    Based on TA indicators, populates the buy trend for the given dataframe
    :param dataframe: DataFrame
    :return: DataFrame with buy column
    """
    prev_sar = dataframe['sar'].shift(1)
    prev_close = dataframe['close'].shift(1)
    prev_sar2 = dataframe['sar'].shift(2)
    prev_close2 = dataframe['close'].shift(2)

    # wait for stable turn from bearish to bullish market
    dataframe.loc[
        (dataframe['close'] > dataframe['sar']) &
        (prev_close > prev_sar) &
        (prev_close2 < prev_sar2),
        'swap'
    ] = 1

    # consider prices above ema to be in upswing
    dataframe.loc[dataframe['ema'] <= dataframe['close'], 'upswing'] = 1

    # Capture last 10 rows and check if they are -1
    # 18 = 1hr30min if candles are every 5min
    temp_data = dataframe.tail(18)

    # candle = -1 or candle = 1 (red or green)
    numb_of_candles = 0
    for candle in temp_data['Trend']:
        if candle == -1:
            numb_of_candles += 1

    dataframe.loc[
        # (dataframe['swap'] == 1) &
        # (dataframe['upswing'] == 1) &
        # (dataframe['adx'] > 25) & # adx over 25 tells there's enough momentum
        # (dataframe['macd'] > dataframe['macds']) &
        # (dataframe['Trend'].tail(4) == -1) & #Being replaced by the last 10 that we calculated above
        (numb_of_candles >= 12) &
        (dataframe['PositionBBANDS'] == 1) &
        (dataframe['PositionSTOCH'] == 1) &
        (dataframe['PositionRSI'] == 1),
        'buy'
    ] = 1

    dataframe.loc[
        (dataframe['buy'] == 1),
        'buy_price'
    ] = dataframe['close']


    return dataframe


def analyze_ticker(pair: str) -> DataFrame:
    """
    Get ticker data for given currency pair, push it to a DataFrame and
    add several TA indicators and buy signal to it
    :return DataFrame with ticker data and indicator data
    """
    minimum_date = arrow.utcnow().shift(hours=-6)
    data = get_ticker(pair, minimum_date)
    dataframe = parse_ticker_dataframe(data['result'], minimum_date)

    # If the length of the dataframe is greater than 1, then we are good 
    # to pull out of the while loop, else we'll keep looping until the error
    # is fixed. (Unknown if this is final fix)
    empty = True

    while empty:
        #logger.debug('Checking if dataframe is empty')
        if len(dataframe.columns) > 1:
            empty = False
            #logger.debug('Dataframe is not empty')
        else:
            data = get_ticker(pair, minimum_date)
            dataframe = parse_ticker_dataframe(data['result'], minimum_date)
            logger.debug('Dataframe is empty; Trying again')

    dataframe = populate_indicators(dataframe)
    dataframe = populate_buy_trend(dataframe)
    return dataframe

def get_buy_signal(pair: str) -> bool:
    """
    Calculates a buy signal based several technical analysis indicators
    :param pair: pair in format BTC_ANT or BTC-ANT
    :return: True if pair is good for buying, False otherwise
    """
    dataframe = analyze_ticker(pair)
    latest = dataframe.iloc[-1]

    # Check if dataframe is out of date
    signal_date = arrow.get(latest['date'].replace('T',''), 'YYYY-MM-DDHH:mm:ss')
    # print (signal_date)
    # print (arrow.now() - timedelta(minutes=10))
    # print(latest['date'].replace('T',''))

    if signal_date < arrow.now() - timedelta(minutes=10):
        return False

    signal = latest['buy'] == 1
    logger.debug('buy_trigger: %s (pair=%s, signal=%s)', latest['date'], pair, signal)
    return signal


def plot_dataframe(dataframe: DataFrame, pair: str) -> None:
    """
    Plots the given dataframe
    :param dataframe: DataFrame
    :param pair: pair as str
    :return: None
    """

    import matplotlib

    matplotlib.use("Qt5Agg")
    import matplotlib.pyplot as plt

    # Two subplots sharing x axis
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    fig.suptitle(pair, fontsize=14, fontweight='bold')
    ax1.plot(dataframe.index.values, dataframe['sar'], 'g_', label='pSAR')
    ax1.plot(dataframe.index.values, dataframe['close'], label='close')
    ax1.plot(dataframe.index.values, dataframe['sell'], 'ro', label='sell')
    ax1.plot(dataframe.index.values, dataframe['ema'], '--', label='EMA(20)')
    ax1.plot(dataframe.index.values, dataframe['buy'], 'bo', label='buy')
    ax1.legend()

    ax2.plot(dataframe.index.values, dataframe['adx'], label='ADX')
    ax2.plot(dataframe.index.values, [25] * len(dataframe.index.values))
    ax2.legend()

    # Fine-tune figure; make subplots close to each other and hide x ticks for
    # all but bottom plot.
    fig.subplots_adjust(hspace=0)
    plt.setp([a.get_xticklabels() for a in fig.axes[:-1]], visible=False)
    plt.show()


if __name__ == '__main__':
    # Install PYQT5==5.9 manually if you want to test this helper function
    while True:
        test_pair = 'BTC_ANT'
        #for pair in ['BTC_ANT', 'BTC_ETH', 'BTC_GNT', 'BTC_ETC']:
        #   get_buy_signal(pair)
        plot_dataframe(analyze_ticker(test_pair), test_pair)
        time.sleep(60)
