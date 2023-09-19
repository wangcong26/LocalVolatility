import pandas as pd
import pandas_datareader.data as web
import numpy as np

# need to add header: https://github.com/pydata/pandas-datareader/issues/923
# https://www.codearmo.com/python-tutorial/options-trading-getting-options-data-yahoo-finance
META = web.YahooOptions('META')
META.headers = {'User-Agent': 'Firefox'}
for expiry in META.expiry_dates:
    print(expiry)

calls = META.get_call_data(month=12, year=2023)
allCalls = META.get_call_data(expiry= META.expiry_dates)
print(allCalls)