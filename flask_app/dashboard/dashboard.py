import dash
from dash import dcc, html, dash_table
import plotly.graph_objs as go
from dash.dependencies import Input, Output, State
import pandas as pd
from datetime import datetime, date
import numerapi
import requests
import io
from .dash import Dash

def init_dashboard(server):

    app = Dash(server=server)

    # get models
    # find better way to do this, eg a daily update on the server instead of doing it every time
    lb = numerapi.NumerAPI().get_leaderboard(99999)
    models = [x['username'] for x in lb]
    currencies = ['GBP', 'EUR', 'USD']

    today = datetime.now()

    app.layout = html.Div([
                            html.Div([
                                html.Div([
                                            dcc.Dropdown(id='model-picker',
                                                options=[{'label': m, 'value': m} for m in models],
                                                multi=True)],
                                    className='column'),
                                html.Div([
                                            dcc.Dropdown(id='currency-picker',
                                                options=[{'label': c, 'value': c} for c in currencies],
                                                multi=False)],
                                    className='column'),
                                html.Div([
                                            dcc.DatePickerRange(id='date-picker',
                                                initial_visible_month=today,
                                                display_format='DD-MM-YYYY',
                                                end_date=today)],
                                    className='column'),
                                html.Div([html.Button(id='submit-button',
                                            n_clicks=0,
                                            children='Submit',
                                            className='button is-fullwidth')],
                                    className='column')
                                        ], className='columns'),
                                html.Div(id='total-display', className='box is-size-3'),
                                html.Div(dcc.Graph(id='graph'), className='block'),
                                html.Div(dash_table.DataTable(
                                                                id='table'), className='block')
                                                        ])

    @app.callback(
                    Output('total-display', 'children'),
                    Output('graph', 'figure'),
                    Output('table', 'data'),
                    [Input('submit-button', 'n_clicks')],
                    [State('model-picker', 'value'),
                    State('currency-picker', 'value'),
                    State('date-picker', 'start_date'),
                    State('date-picker', 'end_date')])
    def calculate_payouts(n_clicks, model_list, currency, start, end):

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
           'model': 'Model', 'roundNumber': 'Round', 'payout': 'NMR Payout', 'roundResolveTime': 'Round Resolved'}

        # select and rename columns
        df = df[[key for key in mapper]].rename(mapper, axis=1)

        # drop nans from payout
        df = df.dropna(subset = ['NMR Payout'])
        df['NMR Payout'] = df['NMR Payout'].astype('float64')

        # set time to midnight and remove local time zone
        df['Round Resolved'] = df['Round Resolved'].apply(lambda x: x.replace(hour=0, minute=0, second=0))
        df['Round Resolved'] = pd.to_datetime(df['Round Resolved']).dt.tz_localize(None)

        # restrict to dates specified
        start = datetime.fromisoformat(start)
        end = datetime.fromisoformat(end)
        df = df[(df['Round Resolved'] >= start) & (df['Round Resolved'] <= end)]

        # currency data
        epoch_start = int(start.timestamp())
        epoch_end = int(end.timestamp())

        url = f"https://query1.finance.yahoo.com/v7/finance/download/NMR-{currency}?period1={epoch_start}&period2={epoch_end}&interval=1d&events=history&includeAdjustedClose=true"
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

        response = requests.get(url, headers=headers)
        curr = pd.read_csv(io.StringIO(response.content.decode('utf-8')), parse_dates=['Date'])
        curr = curr[['Date', 'Close']]

        # merge together
        df = df.merge(curr, how='left', left_on='Round Resolved', right_on='Date')
        df = df.drop(columns='Date')
        df['Round Resolved'] = df['Round Resolved'].apply(lambda x: x.date())
        df = df.rename({'Close': f'{currency}/NMR'}, axis=1)
        df[f'{currency} Payout'] = df['NMR Payout'] * df[f'{currency}/NMR']

        for col in ['NMR Payout', f'{currency}/NMR', f'{currency} Payout']:
            df[col] = df[col].apply(lambda x: round(x, 2))

        total_nmr = round(df['NMR Payout'].sum(), 2)
        total_curr = round(df[f'{currency} Payout'].sum(), 2)

        data = [go.Scatter(x=df[df['Model'] == m]['Round Resolved'],
                            y=df[df['Model'] == m][f'{currency} Payout'],
                            name=m,
                            mode='lines') for m in model_list]
        figure = {'data': data,
                    'layout': go.Layout(title=f'{currency} Payout', hovermode='closest')}

        return f"NMR: {total_nmr}\n{currency}: {total_curr}", figure, df.to_dict('records')

    return app.server
