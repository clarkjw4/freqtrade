from persistence import Trade
from datetime import timedelta
from sqlalchemy import and_, func, text
import arrow
import datetime
import exchange
import analyze


class Message:

	def get_status(self, trades):

		messages = []

		for trade in trades:
			# calculate profit and send message to user
			current_rate = exchange.get_ticker(trade.pair)['bid']
			current_profit = 100 * ((current_rate - trade.open_rate) / trade.open_rate)
			orders = exchange.get_open_orders(trade.pair)
			orders = [o for o in orders if o['id'] == trade.open_order_id]
			order = orders[0] if orders else None

			fmt_close_profit = '{:.2f}%'.format(
			    round(trade.close_profit, 2)
			) if trade.close_profit else None
			markdown_msg = """
*Trade ID:* `{trade_id}`
*Current Pair:* [{pair}]({market_url})
*Open Since:* `{date}`
*Amount:* `{amount}`
*Open Rate:* `{open_rate}`
*Close Rate:* `{close_rate}`
*Current Rate:* `{current_rate}`
*Close Profit:* `{close_profit}`
*Current Profit:* `{current_profit:.2f}%`
*Open Order:* `{open_order}`
			""".format(
				trade_id=trade.id,
				pair=trade.pair,
				market_url=exchange.get_pair_detail_url(trade.pair),
				date=arrow.get(trade.open_date).humanize(),
				open_rate=trade.open_rate,
				close_rate=trade.close_rate,
				current_rate=current_rate,
				amount=round(trade.amount, 8),
				close_profit=fmt_close_profit,
				current_profit=round(current_profit, 2),
				open_order='{} ({})'.format(order['remaining'], order['type']) if order else None,
			)

			messages.append(markdown_msg)

		return messages

	def get_profit(self, trades) -> str:

		profit_amounts = []
		profits = []
		durations = []
		for trade in trades:
			if trade.close_date:
				durations.append((trade.close_date - trade.open_date).total_seconds())
			if trade.close_profit:
				profit = trade.close_profit
			else:
				# Get current rate
				current_rate = exchange.get_ticker(trade.pair)['bid']
				profit = 100 * ((current_rate - trade.open_rate) / trade.open_rate)

			profit_amounts.append((profit / 100) * trade.stake_amount)
			profits.append(profit)

		best_pair = Trade.session.query(Trade.pair, func.sum(Trade.close_profit).label('profit_sum')) \
			.filter(Trade.is_open.is_(False)) \
			.group_by(Trade.pair) \
			.order_by(text('profit_sum DESC')) \
			.first()

		if not best_pair:
			send_msg('*Status:* `no closed trade`', bot=bot)
			return

		bp_pair, bp_rate = best_pair

		markdown_msg = """
	*ROI:* `{profit_btc:.2f} ({profit:.2f}%)`
	*Trade Count:* `{trade_count}`
	*First Trade opened:* `{first_trade_date}`
	*Latest Trade opened:* `{latest_trade_date}`
	*Avg. Duration:* `{avg_duration}`
	*Best Performing:* `{best_pair}: {best_rate:.2f}%`
		""".format(
			profit_btc=round(sum(profit_amounts), 8),
			profit=round(sum(profits), 2),
			trade_count=len(trades),
			first_trade_date=arrow.get(trades[0].open_date).humanize(),
			latest_trade_date=arrow.get(trades[-1].open_date).humanize(),
			avg_duration=str(timedelta(seconds=sum(durations) / float(len(durations)))).split('.')[0],
			best_pair=bp_pair,
			best_rate=round(bp_rate, 2),
		)

		return markdown_msg

	def get_log(self, trades, balances):

		profit_amounts = []
		profits = []
		durations = []
		for trade in trades:
			if trade.close_date:
				durations.append((trade.close_date - trade.open_date).total_seconds())
			if trade.close_profit:
				profit = trade.close_profit
			else:
				# Get current rate
				current_rate = exchange.get_ticker(trade.pair)['bid']
				profit = 100 * ((current_rate - trade.open_rate) / trade.open_rate)

			profit_amounts.append((profit / 100) * trade.stake_amount)
			profits.append(profit)

		best_pair = Trade.session.query(Trade.pair, func.sum(Trade.close_profit).label('profit_sum')) \
			.filter(Trade.is_open.is_(False)) \
			.group_by(Trade.pair) \
			.order_by(text('profit_sum DESC')) \
			.first()

		now = datetime.datetime.now()

		btc_wallet_balance = 0.0
		for balance in balances:
			if balance['Currency'] == "BTC":
				btc_wallet_balance = balance['Balance']

		# In USD
		current_btc_price = analyze.get_btc_current_price()

		usd_wallet_balance = btc_wallet_balance * current_btc_price

		bp_pair, bp_rate = best_pair
		markdown_msg = "{date},{time},{trade_count},{best_pair}: {best_rate:.2f}%,{avg_duration},{profit_btc:.2f} ({profit:.2f}%),{btc_wallet}BTC ({usd_wallet}USD),{price_btc}".format(
			date=str(now.month) + "/" + str(now.day) + "/" + str(now.year),
			time=str(now.hour) + ":" + str(now.minute) + ":" + str(now.second),
			trade_count=len(trades),
			best_pair=bp_pair,
			best_rate=round(bp_rate, 2),
			avg_duration=str(timedelta(seconds=sum(durations) / float(len(durations)))).split('.')[0],
			profit_btc=round(sum(profit_amounts), 8),
			profit=round(sum(profits), 2),
			btc_wallet=btc_wallet_balance,
			usd_wallet=usd_wallet_balance,
			price_btc=current_btc_price,
			#btc_wallet,usd_wallet and price_btc are not implemented yet
		)

		return markdown_msg

	def get_order_log(self):
		data = exchange.get_order_log()

		markdown_msg = "{time},{exchange},{ordertype},{price},{orderid}".format(
			time=data['TimeStamp'],
			exchange=data['Exchange'],
			ordertype=data['OrderType'],
			price=data['Price'],
			orderid=data['OrderUuid'],
		)

		return markdown_msg

	def get_forcesell(self, trade):

		# Get current rate
		current_rate = exchange.get_ticker(trade.pair)['bid']
		# Get available balance
		currency = trade.pair.split('_')[1]
		balance = exchange.get_balance(currency)
		# Execute sell
		profit = trade.exec_sell_order(current_rate, balance)

		message = '*{}:* Selling [{}]({}) at rate `{:f} (profit: {}%)`'.format(
			trade.exchange.name,
			trade.pair.replace('_', '/'),
			exchange.get_pair_detail_url(trade.pair),
			trade.close_rate,
			round(profit, 2)
		)

		return message

	def get_performance(self, pair_rates):

		stats = '\n'.join('{index}. <code>{pair}\t{profit:.2f}%</code>'.format(
			index=i + 1,
			pair=pair,
			profit=round(rate, 2)
		) for i, (pair, rate) in enumerate(pair_rates))

		message = '<b>Performance:</b>\n{}\n'.format(stats)

		return message

	def get_cancelorder(self, trade):

		message = '*{}:* Cancelling [{}]'.format(
			trade.exchange.name,
			trade.pair.replace('_', '/'),
		)

		return message