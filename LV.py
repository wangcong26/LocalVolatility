import os
import sys
import numpy as np
from matplotlib import cm
import matplotlib.pyplot as plt
from matplotlib import ticker
from mpl_toolkits.mplot3d import Axes3D
from scipy.interpolate import griddata
import pandas as pd
import math
import scipy.optimize
from pandas_datareader import data, wb
import pandas_datareader.data as web


class LocalVolatilitySurface():
    def __init__(self, quote):
        self.quote = quote

    def loadData(self, saveData=False):
        option = web.YahooOptions(self.quote)
        option.headers = {'User-Agent': 'Firefox'}
        originalData = option.get_all_data()
        self.underlyingPrice = originalData.iloc[0]["Underlying_Price"]
        self.quoteTime = originalData.iloc[0]["Quote_Time"]
        self.optionData = originalData.copy(deep=True)
        self.optionData.sort_index(inplace=True)

        # Select ITM call/put by slicing a MultiIndex using slice(start, end, step). For example, itmCall K <= 0.9 * S_t; itmPut K >= 1.1 * S_t
        itmCall = self.optionData.loc[(slice(None, self.underlyingPrice * 0.9), slice(None))].loc[(slice(None), slice(None), 'call'), :]
        itmPut = self.optionData.loc[(slice(self.underlyingPrice * 1.1, None), slice(None))].loc[(slice(None), slice(None), 'put'), :]
        self.optionData.drop(itmCall.index, inplace=True)
        self.optionData.drop(itmPut.index, inplace=True)
        self.optionData["Iv"] = self.optionData.apply(lambda f: f["IV"], axis=1)
        self.expiries = self.optionData.index.get_level_values("Expiry").unique().date
        self.listFutureExpiries = [expiry for expiry in self.expiries if expiry > self.quoteTime.date()]
        self.listFutureExpiries.sort()
        self.numFutureExpiries = len(self.listFutureExpiries)

        if saveData:
            self.optionData.to_csv(self.quote + "_allData.csv")
            itmCall.to_csv(self.quote + "_itmCall.csv")
            itmPut.to_csv(self.quote + "_itmPut.csv")

    def get_option_item(self, strike, expiry, type, data):
        try:
            call = data.xs((strike, expiry, type)).iloc[0]
            return call
        except:
            return None

    def get_volatility(self, strike, expiry, data):
        call = self.get_option_item(strike, expiry, 'call', data)
        put = self.get_option_item(strike, expiry, 'put', data)

        if call is None or abs(call.Iv - 0) <= 0.0001:
            if put is not None:
                return put.Iv
            else:
                return 0

        if put is None or abs(put.Iv - 0) <= 0.0001:
            return call.Iv

        return (call.Iv + put.Iv) / 2

    def __day_to_maturity(self, expiry):
        total_seconds = ((expiry - self.quoteTime.date()).total_seconds())
        return round(total_seconds / (365 * 24 * 60 * 60), 5)

    def calculate_sabr(self, a, v, p, F, k, t):
        b = 0.5
        z = v / a * (F * k) ** ((1 - b) / 2) * math.log(F / k)
        ln = (math.sqrt(1 - 2 * p * z + z ** 2) + z - p)
        if ln < 0:
            return 0
        X = math.log(ln / (1 - p))
        part1 = a / ((F * k) ** ((1 - b) / 2))
        part2 = 1 + ((1 / (24 * (F * k) ** (1 - b)) * (1 - b) ** 2 * a ** 2)
                     + 1 / 4 * (a * b * p * v) / ((F * k) ** ((1 - b) / 2))
                     + (2 - 3 * p ** 2) * v ** 2 * 1 / 24) * t
        part3 = 1 + (1 / 24 * (1 - b) ** 2 * (math.log(F / k)) ** 2) + (1 / 1920 * (1 - b) ** 4 * (math.log(F / k) ** 4))

        result = part1 * part2 / part3 * (z / X)
        return result

    def __solver_fitted_iv_function(self, data, t, s):

        print("Solver fitted implied volatility function...")

        # fitted iv function
        def calculate_var(a, v, p, F, k, iv):
            result = self.calculate_sabr(a, v, p, F, k, t)
            var = ((iv - result) / iv) ** 2
            return var

        def F(x):
            params = data
            a = x[0]
            v = x[1]
            p = x[2]

            params.loc[:, "Var"] = params.apply(lambda row: calculate_var(a, v, p, s,
                                                                          row.name, row.Iv), axis=1)

            result = params.loc[:, "Var"].sum()

            return result

        bnds = ((0.000001, None), (0.000001, math.sqrt(1 / t)), (-0.999999, 0.999999))
        x = scipy.optimize.minimize(F, [0.5, 0.5, 0.5], bounds=bnds)

        if x.fun > 2.0:
            data.drop(data[data["Iv"] == min(data.Iv)].index, inplace=True)
            data.drop(data[data["Iv"] == max(data.Iv)].index, inplace=True)
            return self.__solver_fitted_iv_function(data, t, s)

        fitted_params = x.x

        print("Function solved. Function value: " + str(x.fun))
        # print(x)
        return fitted_params

    def cleaned_maturity_data(self, expiry):
        filteredData = self.optionData
        data = filteredData.loc[(slice(None), expiry, slice(None)), :]
        otmPut = data.loc[slice(None, self.underlyingPrice), ["Last"]]
        times = 0

        for index in range(len(otmPut) - 1, -1, -1):
            row = otmPut.iloc[index]

            if row.Last == 0.01:
                times = times + 1

            if times > 2:
                data.drop(row.name, inplace=True)

        otmCall = data.loc[slice(self.underlyingPrice, None), ["Last"]]
        times = 0

        for index in range(0, len(otmCall)):
            row = otmCall.iloc[index]
            if row.Last == 0.01:
                times = times + 1

            if times > 2:
                data.drop(row.name, inplace=True)

        return data.loc[data["Last"] > 0]

    def get_market_volatility_data(self, expiry):
        data = self.cleaned_maturity_data(expiry)
        strikes = data.index.get_level_values(0).unique()
        spotData = pd.DataFrame(None, index=strikes, columns=["Iv"])
        spotData.loc[:, "Iv"] = spotData.apply(lambda row: self.get_volatility(row.name, expiry, data), axis=1)
        spotData = spotData.loc[(spotData["Iv"] > 0.05) & (spotData["Iv"] < 2)]

        return spotData

    def get_smile(self, expiry):
        data = self.get_market_volatility_data(expiry)
        t = self.__day_to_maturity(expiry)
        s = self.underlyingPrice
        params = self.__solver_fitted_iv_function(data, t, s)
        x = params
        a = x[0]
        v = x[1]
        p = x[2]
        data.loc[:, 'FittedIV'] = data.apply(lambda row: calculate_sabr(a, v, p, s,
                                                                        row.name, t), axis=1)
        return data

    def show_single_smile(self, expiry):
        spotData = self.get_smile(expiry)
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.plot(spotData.index, spotData['FittedIV'])
        ax.plot(spotData.index, spotData['Iv'], ls='', marker='o', color='r')
        ax.bar(spotData.index, spotData['Var'], 0.25, color='g')
        plt.title(str(self.quote) + ' Volatility Smile - ' + str(expiry))
        plt.show()

    def get_all_smiles(self, result):
        self.sabrParams = pd.DataFrame(None, columns=["t", "a", "v", "p"])
        strikes = self.optionData.index.get_level_values(0).unique()
        s = self.underlyingPrice
        sk = [e for e in strikes if e > s * 0.7 and e < s * 1.3]
        surfaceData = pd.DataFrame(None, index=sk, columns=result)
        badDataColumns = []
        for expiry in result:
            data = self.get_market_volatility_data(expiry.isoformat())
            if len(data) < 5:
                badDataColumns.append(expiry)
                continue
            t = self.__day_to_maturity(expiry)
            params = self.__solver_fitted_iv_function(data, t, s)
            x = params
            a = x[0]
            v = x[1]
            p = x[2]
            self.sabrParams.loc[len(self.sabrParams), :] = (t, a, v, p)
            surfaceData.loc[:, expiry] = surfaceData.apply(lambda row: self.calculate_sabr(a, v, p, s,
                                                                                           row.name, t), axis=1)

        if len(badDataColumns) > 0:
            surfaceData.drop(badDataColumns, axis=1, inplace=True)

        return surfaceData

    def show_multiple_smile(self, result):
        surfaceData = self.get_all_smiles(result)
        surfaceData.plot()
        plt.title(str(quote) + ' Volatility Smiles')
        plt.show()

    def __ShowChart(self, xx, yy, zz, output, nbchart, color, fig):
        print("Plotting " + output + " surface ...")

        ax = fig.add_subplot(1, 1, nbchart, projection='3d')
        ax.set_title(output)

        surf = ax.plot_surface(xx, yy, zz, rstride=1, cstride=1,
                               alpha=0.65, cmap=color, vmin=zz.min(), vmax=zz.max())
        ax.set_xlabel('S')
        ax.set_ylabel('T')
        ax.set_zlabel(output)
        # Plot 3D contour
        zzlevels = np.linspace(zz.min(), zz.max(), num=3, endpoint=True)
        xxlevels = np.linspace(xx.min(), xx.max(), num=3, endpoint=True)
        yylevels = np.linspace(yy.min(), yy.max(), num=3, endpoint=True)
        cset = ax.contour(xx, yy, zz, zzlevels, zdir='z', offset=zz.min(),
                          cmap=color, linestyles='dashed')
        cset = ax.contour(xx, yy, zz, xxlevels, zdir='x', offset=xx.min(),
                          cmap=color, linestyles='dashed')
        cset = ax.contour(xx, yy, zz, yylevels, zdir='y', offset=yy.max(),
                          cmap=color, linestyles='dashed')
        for c in cset.collections:
            c.set_dashes([(0, (2.0, 2.0))])  # Dash contours
        plt.clabel(cset, fontsize=8, inline=1)
        ax.set_xlim(xx.min(), xx.max())
        ax.set_ylim(yy.min(), yy.max())
        ax.set_zlim(zz.min(), zz.max())

        for tick in ax.xaxis.get_major_ticks():
            tick.label.set_fontsize(6)
        for tick in ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(6)
        for tick in ax.zaxis.get_major_ticks():
            tick.label.set_fontsize(6)

        plt.xticks(np.arange(xx.min(), xx.max(), ((xx.max() - xx.min()) / 3)))
        plt.yticks(np.arange(yy.min(), yy.max(), ((yy.max() - yy.min()) / 3)))

        # Colorbar
        colbar = plt.colorbar(surf, shrink=1.0, extend='both', aspect=10)
        l, b, w, h = plt.gca().get_position().bounds
        ll, bb, ww, hh = colbar.ax.get_position().bounds
        colbar.ax.set_position([ll, b + 0.1 * h, ww, h * 0.8])
        tick_locator = ticker.MaxNLocator(nbins=4)
        colbar.locator = tick_locator
        colbar.update_ticks()

    def show_implied_volatility_surface(self):
        surfaceData = self.get_all_smiles(self.listFutureExpiries)
        sk = surfaceData.index
        s = self.underlyingPrice
        X = [k / s for k in surfaceData.index]
        Y = [self.__day_to_maturity(e) for e in surfaceData.columns if self.__day_to_maturity(e) < 1]
        yList = Y
        xAxis = X
        X, Y = np.meshgrid(X, Y)

        def find_iv(k, e):
            ix = xAxis.index(k)
            iy = yList.index(e)
            return surfaceData.iloc[ix][iy]

        fitfunc = np.vectorize(find_iv)
        Z = fitfunc(X, Y)

        fig = plt.figure()
        plt.savefig('test.png')
        color = cm.jet

        self.__ShowChart(X, Y, Z, " Implied Volatility", 1, color, fig)
        # Show subplots
        plt.title(str(self.quote) + ' Implied Volatility Surface')
        plt.savefig("ImpliedVolSurface.png")
        # plt.show()

    def show_smooth_iv_surface(self):
        # self.sabrParams.plot(x=self.sabrParams.t, y=['a', 'v', 'p'])
        # plt.show()

        degree = math.floor(len(self.sabrParams) / 3)

        x = self.sabrParams.t.tolist()
        y_a = ((self.sabrParams.a) ** (-2)).tolist()
        z = np.polyfit(x, y_a, degree)
        a_p = np.poly1d(z)

        y_p = ((self.sabrParams.p) ** (-1)).tolist()
        z = np.polyfit(x, y_p, degree)
        p_p = np.poly1d(z)

        y_v = ((self.sabrParams.v) ** (-2)).tolist()
        z = np.polyfit(x, y_v, degree)
        v_p = np.poly1d(z)

        def plot_params(fitFun, power, title):
            tr = (0, 180 / 365)
            x_fit = np.linspace(tr[0], tr[1], 90)
            y_fit = fitFun(x_fit) ** power
            plt.plot(x_fit, y_fit, label=title)
            print("Saving: ", title, " figure..")
            plt.savefig(title + '.png')
            # plt.show()

        plot_params(a_p, -0.5, "a")
        plot_params(p_p, -1, "p")
        plot_params(v_p, -0.5, "v")

        def __fitted_iv(F, k, t):
            a = (a_p(t)) ** (-1 / 2)
            p = (p_p(t)) ** (-1)
            v = (v_p(t)) ** (-1 / 2)
            iv = self.calculate_sabr(a, v, p, F, k, t)
            if math.isnan(iv):
                print(t, a, p, v, v_p(t))
                raise Exception('number is nan. ' + str((t, a, p, v)))
            return iv

        band = 0.2
        tr = (0.05, 1)
        xi = np.linspace(self.underlyingPrice * (1 - band),
                         self.underlyingPrice * (1 + band), 50)
        yi = np.arange(tr[0], tr[1], 7 / 365)

        X, Y = np.meshgrid(xi, yi)
        fitfunc = np.vectorize(__fitted_iv)
        Z = fitfunc(self.underlyingPrice, X, Y)

        fittedSurface = pd.DataFrame(0.0, index=xi, columns=yi)
        for index, row in fittedSurface.iterrows():
            for col in fittedSurface.columns:
                row[col] = __fitted_iv(self.underlyingPrice, index, col)

        fig = plt.figure()
        color = cm.jet
        self.__ShowChart(X, Y, Z, "Volatility", 1, color, fig)
        # Show subplots
        plt.title(str(self.quote) + ' Smoothed Implied Volatility Surface')
        plt.show()
        self.fittedIVSurface = fittedSurface
        return self.fittedIVSurface

    def cal_local_volatility(self, vol, T, t1, k, k1, k2, vol_k_1, vol_k_2, vol_t_1):
        s = self.underlyingPrice
        r = 0.01
        d1 = (math.log(s / k) + (r + 1 / 2 * (vol ** 2)) * T) / (vol * math.sqrt(T))
        f_t = (vol - vol_t_1) / (T - t1)
        f_k = (vol - vol_k_1) / (k - k1)
        s_k = (vol - 2 * vol_k_1 + vol_k_2) / ((k - k2) ** 2)
        numer = vol ** 2 + 2 * vol * T * (f_t + r * k * f_k)
        denom = (1 + k * d1 * f_k * math.sqrt(T)) ** 2 + vol * (k ** 2) * T * (s_k - d1 * (f_k ** 2) * math.sqrt(T))
        if (numer / denom < 0):
            print(vol, T, t1, k, k1, k2, vol_k_1, vol_k_2, vol_t_1)
            return 0.0

        local_vol = math.sqrt(numer / denom)
        return local_vol

    def local_voltility(self, ivS):
        mats = ivS.columns.tolist()
        ks = ivS.index.tolist()

        localSurface = pd.DataFrame(0.0, index=ks[2:], columns=mats[1:])

        for i in range(1, len(mats)):
            T = mats[i]
            t1 = mats[i - 1]
            for j in range(2, len(ks)):
                vol = ivS.iloc[j, i]
                k = ks[j]
                k1 = ks[j - 1]
                k2 = ks[j - 2]
                vol_k_1 = ivS.iloc[j - 1, i]
                vol_k_2 = ivS.iloc[j - 2, i]
                vol_t_1 = ivS.iloc[j, i - 1]
                # print(vol, T, t1, k, k1, k2, vol_k_1, vol_k_2, vol_t_1)
                localSurface.iloc[j - 2, i - 1] = self.cal_local_volatility(vol,
                                                                            T,
                                                                            t1,
                                                                            k,
                                                                            k1,
                                                                            k2,
                                                                            vol_k_1,
                                                                            vol_k_2,
                                                                            vol_t_1)
        return localSurface

    def show_local_volatility_surface(self):
        lvs = self.local_voltility(self.fittedIVSurface)
        X = lvs.index.tolist()
        Y = lvs.columns.tolist()
        yList = Y
        xAxis = X
        X, Y = np.meshgrid(X, Y)

        def find_iv(k, e):
            ix = xAxis.index(k)
            iy = yList.index(e)
            return lvs.iloc[ix, iy]

        fitfunc = np.vectorize(find_iv)
        Z = fitfunc(X, Y)
        fig = plt.figure()
        color = cm.jet
        self.__ShowChart(X, Y, Z, "Local Volatility", 1, color, fig)
        plt.title(str(self.quote) + ' Local Volatility Surface')
        plt.show()


if __name__ == "__main__":
    # quote = input("Input Stock:")
    quote = "SPY"
    lv = LocalVolatilitySurface(quote)
    lv.loadData(saveData=True)

    lv.show_implied_volatility_surface()
    lv.show_smooth_iv_surface()
    lv.show_local_volatility_surface()
