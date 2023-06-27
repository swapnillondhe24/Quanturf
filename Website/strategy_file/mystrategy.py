import blankly
from blankly import StrategyState
import quanturf_blankly
import os

quanturf_blankly.environment(os.path.abspath(os.path.dirname(__file__)))

def init(symbol, state: StrategyState):
    interface = state.interface
    resolution = state.resolution
    variables = state.variables
    variables['history'] = interface.history(symbol, 800, resolution, return_as='deque')['close']
    variables['has_bought'] = False
    variables['buy_price']=0


def price_event(price, symbol, state: StrategyState):
    # allow the resolution to be any resolution: 15m, 30m, 1d, etc.
    variables = state.variables
    
    variables['history'].append(price)
    if variables['has_bought']:
        order=state.interface.market_order(symbol, 'sell', 1)
        variables['has_bought']=False
        quanturf_blankly.sh_order(order,price)
    else:
        order=state.interface.market_order(symbol, 'buy', 2)
        variables['buy_price']=price
        variables['has_bought']=True
        quanturf_blankly.sh_order(order,price)

if __name__ == "__main__":
    exchange = blankly.Alpaca()
    quanturf_blankly.run_strategy(exchange,price_event,'AAPL','15s',init)

