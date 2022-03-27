import dash
from dash import dcc, html, dash_table
import plotly.graph_objs as go
from dash.dependencies import Input, Output, State
import pandas as pd
from datetime import datetime, date
import numerapi
import requests
import io

app = dash.Dash()
server = app.server

# get models
# find better way to do this, eg a daily update on the server instead of doing it every time
lb = numerapi.NumerAPI().get_leaderboard(99999)
models = [x['username'] for x in lb]

today = datetime.now()

app.layout = html.Div([html.H1('Numerai Payouts Dashboard'),
                        html.Div([
                            html.Div([html.H2('Select models:'),
                                        dcc.Dropdown(id='model-picker',
                                            options=[{'label': m, 'value': m} for m in models],
                                            multi=True)],
                                style={'verticalAlign': 'top', 'width': '30%', 'display': 'inline-block'}),
                            html.Div([html.H2('Select start and end dates:'),
                                        dcc.DatePickerRange(id='date-picker',
                                            initial_visible_month=today,
                                            display_format='DD-MM-YYYY',
                                            end_date=today)],
                                style={'paddingLeft': '20', 'display': 'inline-block'}),
                            html.Div([html.Button(id='submit-button',
                                        n_clicks=0,
                                        children='Submit',
                                        style={'fontSize': 24})],
                                style={'paddingLeft': '20', 'display': 'inline-block'})
                                    ]),
                        # html.Div([dcc.Graph(id='prices-plot',
                        #                     figure={'data': [],
                        #                             'layout': go.Layout(title='Prices')})]),
                            html.Div(id='total-display'),
                            html.Div(dash_table.DataTable(id='table'))
                                                    ])

@app.callback(
                Output('total-display', 'children'),
                Output('table', 'data'),
                [Input('submit-button', 'n_clicks')],
                [State('model-picker', 'value'),
                State('date-picker', 'start_date'),
                State('date-picker', 'end_date')])
def get_total(n_clicks, model_list, start, end):

    if model_list is None:
        return 0

    # round performances
    napi = numerapi.NumerAPI()
    to_concat = []
    for model in model_list:
        df = pd.DataFrame(napi.round_model_performances(model))
        df['model'] = model
        to_concat.append(df)

    df = pd.concat(to_concat)

    mapper = {
       'model': 'Model', 'roundNumber': 'Round', 'payout': 'Payout', 'roundPayoutFactor': 'Payout Factor',
       'roundResolveTime': 'Round Resolved',
       'selectedStakeValue': 'Stake'}

    # select and rename columns
    df = df[[key for key in mapper]].rename(mapper, axis=1)

    # drop nans from payout
    df = df.dropna(subset = ['Payout'])
    df['Payout'] = df['Payout'].astype('float64')
    total_nmr = df['Payout'].sum()

    # set time to midnight and remove local time zone
    df['Round Resolved'] = df['Round Resolved'].apply(lambda x: x.replace(hour=0, minute=0, second=0))
    df['Round Resolved'] = pd.to_datetime(df['Round Resolved']).dt.tz_localize(None)

    # restrict to dates specified
    start = datetime.fromisoformat(start)
    end = datetime.fromisoformat(end)
    df = df[(df['Round Resolved'] >= start) & (df['Round Resolved'] <= end)]

    # gbp data
    epoch_start = int(start.timestamp())
    epoch_end = int(end.timestamp())

    url = f"https://query1.finance.yahoo.com/v7/finance/download/NMR-GBP?period1={epoch_start}&period2={epoch_end}&interval=1d&events=history&includeAdjustedClose=true"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

    response = requests.get(url, headers=headers)
    gbp = pd.read_csv(io.StringIO(response.content.decode('utf-8')), parse_dates=['Date'])
    gbp = gbp[['Date', 'Close']]

    # merge together
    df = df.merge(gbp, how='left', left_on='Round Resolved', right_on='Date')
    df['GBP Payout'] = df['Payout'] * df['Close']
    total_gbp = df['GBP Payout'].sum()

    return f"NMR: {total_nmr}\nGBP: {total_gbp}", df.to_dict('records')

if __name__ == '__main__':
    app.run_server()
