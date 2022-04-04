# update model list and currency conversion tables, in this case hourly

from apscheduler.schedulers.blocking import BlockingScheduler
import numerapi
import json
import time
import requests
import io
import pandas as pd

sched = BlockingScheduler()

@sched.scheduled_job('interval', hours=1)
def do_updates():

    # models
    models = []
    for lb in ['v2Leaderboard']: # to do: add signalsLeaderboard
        qry = f'''
                query {{
                  {lb} {{
                    username
                  }}
                }}
                '''
        usernames = numerapi.NumerAPI().raw_query(qry)['data'][lb]
        models += [x['username'] for x in usernames]
        models.sort()

        with open('data/models.txt', 'w') as f:
            f.write(json.dumps(models))

        print('Updated models.txt')

    # currency tables
    currencies = ['AUD', 'CAD', 'EUR', 'GBP', 'USD']

    for currency in currencies:

        curr = pd.read_csv(f"data/{currency}.csv", parse_dates=['Date'], index_col='Date')
        latest_date = int(curr.index.max().timestamp())
        latest_date -= 259200 # subtract 3 days for overlap

        url = f"https://query1.finance.yahoo.com/v7/finance/download/NMR-{currency}?period1={latest_date}&period2={int(time.time())}&interval=1d&events=history&includeAdjustedClose=true"
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

        response = requests.get(url, headers=headers)
        curr_new = pd.read_csv(io.StringIO(response.content.decode('utf-8')), parse_dates=['Date'], index_col='Date')
        curr_new = curr_new[['Close']]

        curr = pd.concat([curr.reset_index(), curr_new.reset_index()]).drop_duplicates(subset='Date', keep='last').set_index('Date')
        curr.to_csv(f"data/{currency}.csv")

        print(f"Updated {currency}.csv")

sched.start()
