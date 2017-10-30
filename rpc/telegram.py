import logging
import datetime
from typing import Callable, Any
import os

from telegram.error import NetworkError
from telegram.ext import CommandHandler, Updater
from telegram import ParseMode, Bot, Update
from sqlalchemy import and_, func, text

from misc import get_state, State, update_state
from persistence import Trade

import exchange
import main
import log
import message

# Remove noisy log messages
logging.getLogger('requests.packages.urllib3').setLevel(logging.INFO)
logging.getLogger('telegram').setLevel(logging.INFO)
logger = logging.getLogger(__name__)

_updater = None
_CONF = {}
btc_logger = log.Logger()
messager = message.Message()


def init(config: dict) -> None:
    """
    Initializes this module with the given config,
    registers all known command handlers
    and starts polling for message updates
    :param config: config to use
    :return: None
    """
    global _updater
    _updater = Updater(token=config['telegram']['token'], workers=0)

    _CONF.update(config)

    # Register command handler and start telegram message polling
    handles = [
        CommandHandler('status', _status),
        CommandHandler('profit', _profit),
        CommandHandler('start', _start),
        CommandHandler('stop', _stop),
        CommandHandler('forcesell', _forcesell),
        CommandHandler('performance', _performance),
        CommandHandler('cancelorder', _cancelorder),
        CommandHandler('log', _log),
        CommandHandler('schedulelog', _schedule_log),
        CommandHandler('stoplog', _stop_log),
    ]
    for handle in handles:
        _updater.dispatcher.add_handler(handle)
    _updater.start_polling(
        poll_interval=1.0,
        clean=True,
        bootstrap_retries=3,
        timeout=60,
        read_latency=120,
    )
    logger.info(
        'rpc.telegram is listening for following commands: %s',
        [h.command for h in handles]
    )


def authorized_only(command_handler: Callable[[Bot, Update], None]) -> Callable[..., Any]:
    """
    Decorator to check if the message comes from the correct chat_id
    :param command_handler: Telegram CommandHandler
    :return: decorated function
    """
    def wrapper(*args, **kwargs):
        bot, update = kwargs.get('bot') or args[0], kwargs.get('update') or args[1]

        if not isinstance(bot, Bot) or not isinstance(update, Update):
            raise ValueError('Received invalid Arguments: {}'.format(*args))

        chat_id = int(_CONF['telegram']['chat_id'])
        if int(update.message.chat_id) == chat_id:
            logger.info('Executing handler: %s for chat_id: %s', command_handler.__name__, chat_id)
            return command_handler(*args, **kwargs)
        else:
            logger.info('Rejected unauthorized message from: %s', update.message.chat_id)
    return wrapper


@authorized_only
def _status(bot: Bot, update: Update) -> None:
    """
    Handler for /status.
    Returns the current TradeThread status
    :param bot: telegram bot
    :param update: message update
    :return: None
    """
    # Fetch open trade
    trades = Trade.query.filter(Trade.is_open.is_(True)).all()
    if get_state() != State.RUNNING:
        send_msg('*Status:* `trader is not running`', bot=bot)
    elif not trades:
        send_msg('*Status:* `no active order`', bot=bot)
    else:
        messages = messager.get_status(trades)

        for message in messages:
            send_msg(message, bot=bot)


@authorized_only
def _profit(bot: Bot, update: Update) -> None:
    """
    Handler for /profit.
    Returns a cumulative profit statistics.
    :param bot: telegram bot
    :param update: message update
    :return: None
    """
    trades = Trade.query.order_by(Trade.id).all()

    markdown_msg = messager.get_profit(trades)
    send_msg(markdown_msg, bot=bot)

@authorized_only
def _log(bot: Bot, update: Update) -> None:
    """
    Handler for /log
    Logs to a csv file profit statistics among other things (unknown right now)
    :param bot: telegram bot
    :param update: message update
    :return: None
    """
    trades = Trade.query.order_by(Trade.id).all()
    balances = exchange.get_balances()
    markdown_msg = messager.get_log(trades, balances)
    btc_logger.log(markdown_msg) 
    filepath_trades = os.path.dirname(os.path.abspath('log.csv'))
    send_msg('Log (Trades) Created: file:///{path}'.format(path=filepath_trades))

    # Order Logs
    limit = btc_logger.limit_order_log()
    order_messages = messager.get_order_log(limit)
    filepath_orders = os.path.dirname(os.path.abspath('order_log.csv'))
    for message in order_messages:
        btc_logger.log(message, "order_log.csv")
    send_msg('Log (Orders) Created: file:///{path}'.format(path=filepath_orders))

@authorized_only
def _schedule_log(bot: Bot, update: Update) -> None:

    try:
        time = int(update.message.text
                       .replace('/schedulelog', '')
                       .strip())

        btc_logger.start_scheduled_log(time)
        send_msg('Auto-Generate logs every {0} hour(s)'.format(time))

    except ValueError:
        send_msg('Invalid argument. Usage: `/schedulelog <time [in hours]>`')
        logger.warning('/schedulelog: Invalid argument received')

@authorized_only
def _stop_log(bot: Bot, update: Update) -> None:
    btc_logger.stop_scheduled_log()
    send_msg('Scheduled log has been canceled')

@authorized_only
def _start(bot: Bot, update: Update) -> None:
    """
    Handler for /start.
    Starts TradeThread
    :param bot: telegram bot
    :param update: message update
    :return: None
    """
    if get_state() == State.RUNNING:
        send_msg('*Status:* `already running`', bot=bot)
    else:
        update_state(State.RUNNING)


@authorized_only
def _stop(bot: Bot, update: Update) -> None:
    """
    Handler for /stop.
    Stops TradeThread
    :param bot: telegram bot
    :param update: message update
    :return: None
    """
    if get_state() == State.RUNNING:
        send_msg('`Stopping trader ...`', bot=bot)
        update_state(State.STOPPED)
    else:
        send_msg('*Status:* `already stopped`', bot=bot)


# TODO Fix SQlite Bug
@authorized_only
def _forcesell(bot: Bot, update: Update) -> None:
    """
    Handler for /forcesell <id>.
    Sells the given trade at current price
    :param bot: telegram bot
    :param update: message update
    :return: None
    """
    if get_state() != State.RUNNING:
        send_msg('`trader is not running`', bot=bot)
        return

    try:
        trade_id = int(update.message.text
                       .replace('/forcesell', '')
                       .strip())
        # Query for trade
        trade = Trade.query.filter(and_(
            Trade.id == trade_id,
            Trade.is_open.is_(True)
        )).first()
        if not trade:
            send_msg('There is no open trade with ID: `{}`'.format(trade_id))
            return

        message = messager.get_forcesell(trade)

        logger.info(message)
        send_msg(message)
        main.close_trade_if_fulfilled(trade)

    except ValueError:
        send_msg('Invalid argument. Usage: `/forcesell <trade_id>`')
        logger.warning('/forcesell: Invalid argument received')


@authorized_only
def _performance(bot: Bot, update: Update) -> None:
    """
    Handler for /performance.
    Shows a performance statistic from finished trades
    :param bot: telegram bot
    :param update: message update
    :return: None
    """
    if get_state() != State.RUNNING:
        send_msg('`trader is not running`', bot=bot)
        return
    
    pair_rates = Trade.session.query(Trade.pair, func.sum(Trade.close_profit).label('profit_sum')) \
        .filter(Trade.is_open.is_(False)) \
        .group_by(Trade.pair) \
        .order_by(text('profit_sum DESC')) \
        .all()

    message = messager.get_performance(pair_rates)
    logger.debug(message)
    send_msg(message, parse_mode=ParseMode.HTML)

#TODO Fix Method
@authorized_only
def _cancelorder(bot: Bot, update: Update) -> None:
    """
    Handler for /cancelorder <id>.
    Cancels the given trade
    :param bot: telegram bot
    :param update: message update
    :return: None
    """
    if get_state() != State.RUNNING:
        send_msg('`trader is not running`', bot=bot)
        return

    try:
        trade_id = int(update.message.text
                       .replace('/cancelorder', '')
                       .strip())
 
        # Query for trade
        trade = Trade.query.filter(and_(
            Trade.id == trade_id,
            Trade.is_open.is_(True)
        )).first()

        print (trade.pair)

        if not trade:
            send_msg('There is no open trade with ID: `{}`'.format(trade_id))
            return
        # Cancel the order - According to test/test_main.py Line 84
        message = messager.get_cancelorder(trade)
        logger.info(message)
        send_msg(message)
        exchange.cancel_order(trade.open_order_id)
        # main.close_trade_if_fulfilled(trade)

    except ValueError:
        send_msg('Invalid argument. Usage: `/closeorder <trade_id>`')
        logger.warning('/closeorder: Invalid argument received')
        
def send_msg(msg: str, bot: Bot = None, parse_mode: ParseMode = ParseMode.MARKDOWN) -> None:
    """
    Send given markdown message
    :param msg: message
    :param bot: alternative bot
    :param parse_mode: telegram parse mode
    :return: None
    """
    if _CONF['telegram'].get('enabled', False):
        try:
            bot = bot or _updater.bot
            try:
                bot.send_message(_CONF['telegram']['chat_id'], msg, parse_mode=parse_mode)
            except NetworkError as error:
                # Sometimes the telegram server resets the current connection,
                # if this is the case we send the message again.
                logger.warning(
                    'Got Telegram NetworkError: %s! Trying one more time.',
                    error.message
                )
                bot.send_message(_CONF['telegram']['chat_id'], msg, parse_mode=parse_mode)
        except Exception:
            logger.exception('Exception occurred within Telegram API')
