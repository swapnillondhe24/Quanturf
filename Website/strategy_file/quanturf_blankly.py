import blankly
from time import sleep
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from threading import Thread
import alpaca_trade_api as tradeapi
import json
import requests
import pandas as pd
import datetime as dt
import numpy as np
import os

api=""
base_dir=""

def environment(dir_path):
    global api
    global base_dir
    
    base_dir=dir_path
    with open(os.path.join(dir_path, 'keys.json')) as keys_file:
        json_data=json.load(keys_file)
        strategy_name=""
        for x in json_data["alpaca"]:
            strategy_name=x
    
    api=tradeapi.REST(key_id=json_data['alpaca'][strategy_name]['API_KEY'],
                     secret_key=json_data['alpaca'][strategy_name]['API_SECRET'],
                     base_url="https://paper-api.alpaca.markets",
                     api_version='V2')
            

def realized_profit_df_strategy():
    global base_dir
    with open(os.path.join(base_dir, 'transactions.json')) as json_data:
        data = json.load(json_data)
    df = pd.json_normalize(data,record_path=['transaction'])

    result_df = pd.DataFrame(columns = ['Qty','Price','Symbol','Transaction_time','order_id','Type'])
    order_id_list = []
    qty_list = []
    price_list = []
    symbol_list = []
    transaction_time_list = []
    type_list = []

    for index,obj in df.iterrows():
        order_id_list.append(obj["order ID"])
        qty_list.append(obj["Qty"])
        price_list.append(obj["Price"])
        symbol_list.append(obj["Symbol"])
        transaction_time_list.append(obj["Time"])
        type_list.append(obj["Type"])
    
    result_df = pd.DataFrame({
			'order_id':order_id_list,
			'Qty': qty_list, 
			'Price': price_list, 
			'Symbol': symbol_list, 
			'Transaction_time': transaction_time_list, 
			'Type': type_list})
    
    df_buy = result_df[result_df.Type == 'buy']

    df_sell = result_df[result_df.Type == 'sell']

    df = pd.merge(df_buy, df_sell, on = 'Symbol', how = 'right', suffixes = ['_buy','_sell'])

    df_unrealized = result_df[~result_df['Symbol'].isin(df_sell.Symbol.unique())]
    testing = df_sell.sort_values(by = 'Transaction_time')
    convert_dict = {'Price': float}
    testing = testing.astype(convert_dict)
    df_buy = df_buy.astype(convert_dict)
    output_frame = []

    for sym in testing.Symbol.unique():
        buy = df_buy.loc[df_buy.Symbol == sym] 
        sell = testing.loc[testing.Symbol == sym] 

        obs = [] 
        for i, row in sell.iterrows(): 
            output_dict = {}
            if i not in obs:
                out = buy.loc[(buy.Transaction_time < row.Transaction_time)]
                idx = [j for j in out.index if j not in obs]
                if idx != []:
                    out = out.loc[idx]
                else:
                    out=out.loc[obs]
                output_dict = {
								'Symbol': sym, 
								'selling_qty': int(row.Qty),
								'Avg_selling_Price': row.Price,
								'Avg_buying_cost': round(out.groupby('Symbol').Price.mean()[0],2),
								'Sell_time': row.Transaction_time,
								'Profit_per_unit': round(row.Price - out.groupby('Symbol').Price.mean()[0],2),
								'Total_Profit': round((row.Price - out.groupby('Symbol').Price.mean())[0] * int(row.Qty),2),
								'Winning_bet': True if round(row.Price - out.groupby('Symbol').Price.mean()[0],2) > 0 else False}
                output_frame.append(output_dict)
					
                if len(idx) > 1:
                    for ix in idx:
                        obs.append(ix)
    
    return output_frame

def unrealised_profit_df_strategy():

    with open(os.path.join(base_dir, 'transactions.json')) as json_data:
        data = json.load(json_data)
    df = pd.json_normalize(data,record_path=['transaction'])

    sell_order_list=[]
    buy_order_list=[]    

    for index,obj in df.iterrows():
        if obj['Type']=="sell":
            sell_order_list.append({
                "Symbol": obj["Symbol"],
                "Qty": obj["Qty"],
                "price": obj["Price"],
                "Time": obj["Time"],
                "Status": obj["Status"],
                "Type": obj["Type"],
                "order ID": obj["order ID"]
            })
        else:
            buy_order_list.append({
                "Symbol": obj["Symbol"],
                "Qty": obj["Qty"],
                "price": obj["Price"],
                "Time": obj["Time"],
                "Status": obj["Status"],
                "Type": obj["Type"],
                "order ID": obj["order ID"]
            })
            
    for sell_order in reversed(sell_order_list):
        curr_sell_order_symbol = sell_order["Symbol"]
        curr_sell_order_qty = sell_order["Qty"]
        curr_sell_order_transaction_time = sell_order["Time"]

        buy_order_index_that_are_closed = []
        for index, buy_order in reversed(list(enumerate(buy_order_list))):
            curr_buy_order_qty = buy_order["Qty"]
            if curr_sell_order_qty == 0:
                break
            if buy_order["Symbol"] == curr_sell_order_symbol and buy_order["Time"] < curr_sell_order_transaction_time:
                if curr_buy_order_qty <= curr_sell_order_qty:
                    curr_sell_order_qty = curr_sell_order_qty - curr_buy_order_qty
                    buy_order_index_that_are_closed.append(index)
                elif curr_buy_order_qty > curr_sell_order_qty:
                    buy_order["Qty"] = buy_order["Qty"] - curr_sell_order_qty
                    break
        #update the buy order containing only open position orders
        buy_order_list = [item for idx, item in enumerate(buy_order_list) if idx not in buy_order_index_that_are_closed]
    
    account_positions = api.list_positions()
    current_price_dict = {}
    for position in account_positions:
        current_price_dict[position.symbol] = float(position.current_price)
    
    output_frame = []
    
    for res in buy_order_list:
        output_dict = {}
        current_price = current_price_dict[(res["Symbol"]).replace("/", "")]
        output_dict["Symbol"]=res["Symbol"]
        output_dict["Qty"]=res["Qty"]
        output_dict["Price"]=res["price"]
        output_dict["Transaction_Time"]=res["Time"]
        output_dict["Unrealized_Profit"]=round(current_price-res["price"], 2)
        output_dict["Total_Unrealized_Profit"]=round(res["Qty"]*round(current_price-res["price"], 2),2)
        output_frame.append(output_dict)
        
    return output_frame

def get_pnl_df_strategy(open_positions:list, close_positions:list):
     
    #open
    open_df = pd.DataFrame(columns = ['Qty','price','symbol','transaction_time','unrealized_profit','total_unrealized_profit'])
    qty_list = []
    price_list = []
    symbol_list = []
    transaction_time_list = []
    unrealized_profit_list=[]
    total_unrealized_profit_list=[]
    date_list=[]


    for obj in open_positions:
        qty_list.append(obj["Qty"])
        price_list.append(obj["Price"])
        symbol_list.append(obj["Symbol"])
        transaction_time_list.append(obj["Transaction_Time"])
        unrealized_profit_list.append(obj["Unrealized_Profit"])
        total_unrealized_profit_list.append(obj["Total_Unrealized_Profit"])

        time=dt.datetime.utcfromtimestamp(int(obj["Transaction_Time"]))
        time=str(time.hour) + ":" + str(time.minute)
        date_list.append(time)
    
    open_df = pd.DataFrame({
        'Qty':qty_list,
        'price':price_list,
        'symbol':symbol_list,
        'transaction_time':transaction_time_list,
        'unrealized_profit':unrealized_profit_list,
        'total_unrealized_profit':total_unrealized_profit_list,
        'date':date_list,
    })
    
    # open_df['date'] =  pd.to_datetime(open_df['transaction_time'], errors='coerce')
    unrealized_pnl_df = open_df.groupby('date')['total_unrealized_profit'].sum().reset_index()
    
    #close
    close_df=pd.DataFrame(columns=['Sybmol','selling_qty','Avg_selling_Price','Avg_buying_cost','Sell_time','Profit_per_unit','Total_Profit'])
    
    symbol_list=[]
    selling_qty_list=[]
    Avg_selling_Price_list=[]
    Avg_buying_cost_list=[]
    Sell_time_list=[]
    Profit_per_unit_list=[]
    Total_Profit_list=[]
    date_list=[]


    for obj in close_positions:
        symbol_list.append(obj['Symbol'])
        selling_qty_list.append(obj['selling_qty'])
        Avg_selling_Price_list.append(obj['Avg_selling_Price'])
        Avg_buying_cost_list.append(obj['Avg_buying_cost'])
        Sell_time_list.append(obj['Sell_time'])
        Profit_per_unit_list.append(obj['Profit_per_unit'])
        Total_Profit_list.append(obj['Total_Profit'])

        time=dt.datetime.utcfromtimestamp(int(obj['Sell_time']))
        time=str(time.hour) + ":" + str(time.minute)
        date_list.append(time)
    
    close_df=pd.DataFrame({
        'Symbol':symbol_list,
        'selling_qty':selling_qty_list,
        'Avg_selling_Price':Avg_selling_Price_list,
        'Avg_buying_cost':Avg_buying_cost_list,
        'Sell_time':Sell_time_list,
        'Profit_per_unit':Profit_per_unit_list,
        'Total_Profit':Total_Profit_list,
        'date':date_list
    })

    # close_df['date'] = pd.to_datetime(close_df['Sell_time'], errors='coerce')
    realized_pnl_df = close_df.groupby('date')['Total Profit'].sum().reset_index()

    df = pd.merge(unrealized_pnl_df, realized_pnl_df, on='date', how='outer')
    df = df.rename(columns={'Total_Profit': 'realized_pnl', 'total_unrealized_profit': 'unrealized_pnl'})
    df = df.fillna(0)
    df['total_pnl'] = df['realized_pnl'] + df['unrealized_pnl']
     
    return df

def portfolio():

    total_dollar_pnl=0
    total_realized_pnl=0
    total_unrealized_pnl=0
    win_rate=0
    drawdown=0
    total_sell=realized_profit_df_strategy().__len__()
    profit_sell=0
    pnl_vector_list=[]
    
    df=get_pnl_df_strategy(unrealised_profit_df_strategy(),realized_profit_df_strategy())
    output_frame=[]
    for idx in df.index:
        output_dict={
            'date':str(df['date'][idx]),
            'unrealized_pnl':df['unrealized_pnl'][idx],
            'realized_pnl':df['realized_pnl'][idx],
            'total_pnl':df['total_pnl'][idx]
        }
        pnl_vector_list.append(float(df['total_pnl'][idx]))
        total_dollar_pnl+=int(df['total_pnl'][idx])
        total_realized_pnl+=int(df['realized_pnl'][idx])
        total_unrealized_pnl+=int(df['unrealized_pnl'][idx])
        output_frame.append(output_dict)

        if int(df['realized_pnl'][idx]) > 0:
            profit_sell+=1

        
    total_dollar_pnl=round(total_dollar_pnl,2)
    total_realized_pnl=round(total_realized_pnl,2)
    total_unrealized_pnl=round(total_unrealized_pnl,2)
    return_percentage=((10000+(total_realized_pnl))/10000)*100
    return_percentage=round(return_percentage,2)

    account=api.get_account()
    account=account.__dict__
    available_cash=float(account['_raw']['cash'])
    available_cash=round(available_cash,2)

    total_val=10000+total_dollar_pnl
    if total_sell!=0:
        win_rate=(profit_sell/total_sell)*100
        win_rate=round(win_rate,2)

    cum_returns = np.cumsum(pnl_vector_list)
    cum_high = np.maximum.accumulate(cum_returns)
    np.seterr(invalid='ignore')
    drawdown = (cum_high - cum_returns) / cum_high
    drawdown=np.max(drawdown)
    drawdown=round(drawdown,2)

    json_file=open(os.path.join(base_dir, 'transactions.json'),"r")
    data=json.load(json_file)
    data=dict(data)
    container_id=data['container_id']
    json_file.close()
    
    json_data={
        'container_id':container_id,
        'total_dollar_pnl':total_dollar_pnl,
        'total_realized_pnl':total_realized_pnl,
        'total_unrealized_pnl':total_unrealized_pnl,
        'return_percentage':return_percentage,
        'available_cash':available_cash,
        'total_val':total_val,
        'win_rate':win_rate,
        'drawdown':drawdown,
        'pnl':output_frame,
    }
    json_data=json.dumps(json_data)
    URL="https://quanturf.com/api/pnl/"
    headers = {'Content-type': 'application/json'}
    pnl_request=requests.post(url=URL,data=json_data,headers=headers)




def live(exchange,symbol,strategy_name,resolution,init):
    strategy = blankly.Strategy(exchange)
    strategy.add_price_event(strategy_name, symbol, resolution=resolution, init=init)
    strategy.start()

def sh_order(order,price):
    order=order.get_response()
    time=int(order['created_at'])
    order_datetime=dt.datetime.utcfromtimestamp(time)
    order_datetime=str(order_datetime.combine(date=order_datetime.date(),time=order_datetime.time()))
    transaction_data={
            'Symbol':order['symbol'],
            'Qty':order['size'],
            'Price':price,
            'Time':order['created_at'],
            'Status':order['status'],
            'Type':order['side'],
            'order ID':order['id'],
            'Formated_time':order_datetime
        }
    
    json_file=open(os.path.join(base_dir, 'transactions.json'),"r")
    data=json.load(json_file)
    data=dict(data)
    data["transaction"].append(dict(transaction_data))
    json_file.close()
    json_file=open(os.path.join(base_dir, 'transactions.json'),"w")
    json_file.write(json.dumps(data))
    json_file.close()

    json_file=open(os.path.join(base_dir, 'transactions.json'),"r")
    data=json.load(json_file)
    data=dict(data)
   
    close_positions=realized_profit_df_strategy()
    open_positions=unrealised_profit_df_strategy()
    data['open']=open_positions
    data['close']=close_positions
    json_file.close()

    json_file=open(os.path.join(base_dir, 'transactions.json'),"w")
    json_file.write(json.dumps(data))
    json_file.close()

    transaction_data=json.dumps(data)
    URL="https://quanturf.com/api/transaction/"
    headers = {'Content-type': 'application/json'}
    transaction_request=requests.post(url=URL,data=transaction_data,headers=headers)


def cronjob():
    scheduler = BackgroundScheduler()
    scheduler.start()

    trigger = CronTrigger(
        year="*", month="*", day="*", hour="*", minute="*/1", second="0"
    )
    scheduler.add_job(
        portfolio,
        trigger=trigger,
        args=[],
        name="portfolio",
    )
    while True:
        sleep(60)


def run_strategy(exchange,strategy_name,symbol,resolution,init):
    
    t1=Thread(target=live,args=[exchange,symbol,strategy_name,resolution,init])
    t2=Thread(target=cronjob,args=[])
    t1.start()
    t2.start()
    t1.join()
    t2.join()