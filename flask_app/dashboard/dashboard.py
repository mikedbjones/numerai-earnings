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

    currencies = ['AUD', 'CAD', 'EUR', 'GBP', 'USD']

    today = datetime.now()

    app.layout = html.Div([
                            html.Div([
                                html.Div([
                                            dcc.Dropdown(id='model-picker',
                                                options=[{'label': m, 'value': m} for m in models],
                                                multi=True,
                                                placeholder='Select models...')],
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
                    Output('user-df', 'data'),
                    Input('submit-button', 'n_clicks'),
                    State('model-picker', 'value'),
                    State('currency-picker', 'value'),
                    State('date-picker', 'start_date'),
                    State('date-picker', 'end_date'))
    def calculate_payouts(n_clicks, model_list, currency, start, end):

        if model_list is not None:

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

            return f"NMR: {total_nmr}", f"{currency}: {total_curr}", figure, df.to_dict('records'), df.to_json(date_format='iso', orient='split')

        else:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    @app.callback(
                    Output('download-df', 'data'),
                    Input('download-button', 'n_clicks'),
                    State('user-df', 'data'))
    def download_csv(n_clicks, df_json):
        if n_clicks is not None:
            return dcc.send_data_frame(pd.read_json(df_json, orient='split').to_csv, 'data.csv')
        else:
            return None

    return app.server
