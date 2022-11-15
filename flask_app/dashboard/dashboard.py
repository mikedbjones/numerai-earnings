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
import json

def init_dashboard(server):

    app = Dash(server=server)

    # get models
    numerai_models = []
    signals_models = []

    for lb in ['v2Leaderboard', 'signalsLeaderboard']:
            qry = f'''
                    query {{
                      {lb} {{
                        username
                      }}
                    }}
                    '''
            usernames = numerapi.NumerAPI().raw_query(qry)['data'][lb]
            if lb == 'v2Leaderboard':
                numerai_models = [x['username'] for x in usernames]
            elif lb == 'signalsLeaderboard':
                signals_models = [x['username'] for x in usernames]

    numerai_models.sort()
    signals_models.sort()

    currencies = ['AUD', 'BTC', 'CAD', 'CNY', 'EUR', 'ETH', 'GBP', 'INR', 'JPY', 'KRW', 'RUB', 'USD']

    today = datetime.now()

    app.layout = html.Div([
                            html.Div([
                                html.Div([
                                    html.Article(
                                        className='message is-warning',
                                        children=[
                                            html.Div('Update: Added BTC, CNY, ETH, INR, JPY, KRW, RUB.', hidden=False, className='message-body', style={'text-align': 'center'})
                                        ]),
                                    ],
                                    className='column')], className='columns'),
                            html.Div([
                                html.Div([
                                            dcc.Dropdown(id='numerai-model-picker',
                                                options=[{'label': m, 'value': m} for m in numerai_models],
                                                multi=True,
                                                placeholder='Select numerai models...'),
                                            dcc.Dropdown(id='signals-model-picker',
                                                options=[{'label': m, 'value': m} for m in signals_models],
                                                multi=True,
                                                placeholder='Select signals models...')],
                                    className='column'),
                                html.Div([
                                            dcc.Dropdown(id='currency-picker',
                                                options=[{'label': c, 'value': c} for c in currencies],
                                                multi=False,
                                                placeholder='Select currency...')],
                                    className='column'),
                                html.Div([
                                            dcc.DatePickerRange(id='date-picker',
                                                initial_visible_month=today,
                                                end_date=today,
                                                display_format='DD-MM-YYYY')],
                                    className='column'),
                                html.Div([html.Button(id='submit-button',
                                            n_clicks=0,
                                            children='Submit',
                                            className='button is-fullwidth')],
                                    className='column')
                                        ], className='columns'),
                                html.Div([
                                            html.Div(html.Div(
                                                            id='total-display-nmr',
                                                            className='box is-size-3',
                                                            style={'text-align': 'center'}), className='column'),
                                            html.Div(html.Div(
                                                            id='total-display-curr',
                                                            className='box is-size-3',
                                                            style={'text-align': 'center'}), className='column')],
                                                className='columns is-centered'),
                                html.Div(dcc.Graph(id='graph'), className='block'),
                                html.Div(dash_table.DataTable(
                                                                id='table',
                                                                sort_action='native'), className='block'),
                                html.Div([
                                            html.Button('Download CSV', id='download-button', className='button is-fullwidth'),
                                            dcc.Download(id='download-df')], className='block'),
                                            dcc.Store(id='user-df')
                                                        ])

    @app.callback(
                    Output('total-display-nmr', 'children'),
                    Output('total-display-curr', 'children'),
                    Output('graph', 'figure'),
                    Output('table', 'data'),
                    Output('table', 'columns'),
                    Output('user-df', 'data'),
                    Input('submit-button', 'n_clicks'),
                    State('numerai-model-picker', 'value'),
                    State('signals-model-picker', 'value'),
                    State('currency-picker', 'value'),
                    State('date-picker', 'start_date'),
                    State('date-picker', 'end_date'))
    def calculate_payouts(n_clicks, numerai_model_list, signals_model_list, currency, start, end):

        if numerai_model_list is not None or signals_model_list is not None:

            # round performances
            napi = numerapi.NumerAPI()
            sapi = numerapi.SignalsAPI()
            to_concat = []

            if numerai_model_list is not None:
                for model in numerai_model_list:
                    df = pd.DataFrame(napi.round_model_performances(model))
                    df['model'] = model
                    df['tourn'] = 'numerai'
                    to_concat.append(df)

            if signals_model_list is not None:
                for model in signals_model_list:
                    df = pd.DataFrame(sapi.round_model_performances(model))
                    df['model'] = model
                    df['tourn'] = 'signals'
                    to_concat.append(df)

            df = pd.concat(to_concat)

            mapper = {
               'model': 'Model',
               'tourn': 'Tournament',
               'roundNumber': 'Round',
               'payout': 'NMR Payout',
               'roundResolveTime': 'Round Resolved'}

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

            total_nmr = f"{round(df['NMR Payout'].sum(), 4):.4f}"
            total_curr = f"{round(df[f'{currency} Payout'].sum(), 2):.2f}"

            formatted = {'locale': {}, 'nully': '', 'prefix': None, 'specifier': '.2f'}

            columns_2f = [col for col in df.columns if col in [
                                                                f'{currency}/NMR',
                                                                f'{currency} Payout',
                                                                'NMR Payout']]

            columns_other = [col for col in df.columns if col not in columns_2f]

            table_columns_2f = [
                                    {
                                        "name": i,
                                        "id": i,
                                        "type": "numeric",
                                        "format": formatted
                                    }
                                    for i in columns_2f
                                ]

            table_columns_other = [
                                        {
                                            "name": i,
                                            "id": i
                                        }
                                        for i in columns_other
                                    ]

            table_columns = table_columns_other + table_columns_2f

            data = []

            if numerai_model_list is not None:
                numerai_data = [go.Scatter(x=df[(df['Model'] == m) & (df['Tournament'] == 'numerai')]['Round Resolved'],
                                y=df[(df['Model'] == m) & (df['Tournament'] == 'numerai')][f'{currency} Payout'],
                                name=f'{m} (numerai)',
                                mode='lines') for m in numerai_model_list]
                data += numerai_data

            if signals_model_list is not None:
                signals_data = [go.Scatter(x=df[(df['Model'] == m) & (df['Tournament'] == 'signals')]['Round Resolved'],
                                y=df[(df['Model'] == m) & (df['Tournament'] == 'signals')][f'{currency} Payout'],
                                name=f'{m} (signals)',
                                mode='lines') for m in signals_model_list]
                data += signals_data

            figure = {'data': data,
                        'layout': go.Layout(title=f'{currency} Payout', hovermode='closest')}

            print(df.head(1))
            print(table_columns)
            return f"NMR: {total_nmr}", f"{currency}: {total_curr}", figure, df.to_dict('records'), table_columns, df.to_json(date_format='iso', orient='split')

        else:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    @app.callback(
                    Output('download-df', 'data'),
                    Input('download-button', 'n_clicks'),
                    State('user-df', 'data'))
    def download_csv(n_clicks, df_json):
        if n_clicks is not None:
            return dcc.send_data_frame(pd.read_json(df_json, orient='split').to_csv, 'data.csv', index=False)
        else:
            return None

    return app.server
