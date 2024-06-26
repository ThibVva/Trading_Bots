from AlgorithmImports import *

'''
TRADING BOT Presentation:

This Trading Bot works on the QuantConnect platform, using QuantConnect librairies and integrated Interactive Brokers' API

Strategy : New Highs Momentum
    Check the highest quotes from a lookback period, that is adjusted dynamically based on the underlying volatily
    When quotes are at a highest in the lookback period, Portfolio buys SPY
    A trailing Stop Loss orders is initiated

StopLoss: stop loss a 5% du prix d'entrée, puis si le stock monte passe a 10% de stop loss
Logs: Sell & Buy events
Underlying : SPY

'''

class ShyMole(QCAlgorithm):

#pour choisir la durée sur laquelle on regarde les high depend de la lookback

    def Initialize(self):
        self.SetStartDate(2010, 1, 1)
        self.SetEndDate(2024, 1, 1)
        self.SetCash(1000000)

        self.spy = self.AddEquity("SPY", Resolution.Daily).Symbol

        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        self.SetBenchmark("SPY")

        #1er bug live 12/12/22 : on initialise ces 2 variables de EveryMarketOpen
        self.high = self.History(self.spy, timedelta(240), Resolution.Daily)["high"]
        self.low = self.History(self.spy, timedelta(240), Resolution.Daily)["low"]

        #lookback length & SMA
        self.lookback = 20
        self.ceiling, self.floor = 30, 10
        
        self.sma = self.SMA(self.spy, self.lookback, Resolution.Daily)
        #Pour être sur que SMA soit pret au demarrage, on lui pump in de la donnée à l'initialisation
        closing_prices = self.History(self.spy, 30, Resolution.Daily)["close"]
        for time, price in closing_prices.loc[self.spy].items(): #lock in du time et price du SPY dans la data
            self.sma.Update(time, price)

        #initial stop risk a 0.95 (5%). Quand sous jacent is up, si prix trailing stop risk (10%) est plus haut que l'initial * le prix d'entré, met a jour le stop loss
        #permet d'augmenter le stop loss pour take profit le jour ou ca tombe
        self.initialStopRisk = 0.95
        self.trailingStopRisk = 0.9

        #Schedule le call EveryMarketOpen function, 20min after Market Open (caclcul de la lookback period)
        self.Schedule.On(self.DateRules.EveryDay(self.spy), \
                         self.TimeRules.AfterMarketOpen(self.spy, 20), \
                         Action(self.EveryMarketOpen))

    def EveryMarketOpen(self):
        # Dynamically determine lookback length based on 30 day volatility change rate
        close = self.History(self.spy, 31, Resolution.Daily)["close"]
        todayvol = np.std(close[1:31])
        yesterdayvol = np.std(close[0:30])
        deltavol = (todayvol - yesterdayvol) / todayvol
        self.lookback = round(self.lookback * (1 + deltavol))

        # Account for upper/lower limit of lockback length
        if self.lookback > self.ceiling:
            self.lookback = self.ceiling
        elif self.lookback < self.floor:
            self.lookback = self.floor

        # Buy in case of higher than recent highs (lookback*12)
        if not self.Securities[self.spy].Invested and \
                self.Securities[self.spy].Close >= max(self.high[:-1]):
            self.SetHoldings(self.spy, 1)
            self.Log("BUY SPY @" + str(self.Securities[self.spy].Price))
            self.highestPrice = max(self.high[:-1])

        # Create trailing stop loss if invested
        if self.Securities[self.spy].Invested:

            # If no order exists, send stop-loss
            if not self.Transactions.GetOpenOrders(self.spy):
                self.stopMarketTicket = self.StopMarketOrder(self.spy, \
                                                             -self.Portfolio[self.spy].Quantity, \
                                                             self.initialStopRisk * self.highestPrice)

            #Check if the asset's price is higher than highestPrice
            # & trailing stop price is now higher than initial stop loss * initial price
            if self.Securities[self.spy].Close > self.highestPrice and \
                    self.initialStopRisk * self.highestPrice < self.Securities[\
                self.spy].Close * self.trailingStopRisk:

                # Save the new high to highestPrice
                self.highestPrice = self.Securities[self.spy].Close
                # Update the stop price
                updateFields = UpdateOrderFields()
                updateFields.StopPrice = self.Securities[self.spy].Close * self.trailingStopRisk
                self.stopMarketTicket.Update(updateFields)

                # Print the new stop price with Debug()
                self.Debug("Stop Loss level raised to: " + str(updateFields.StopPrice))

            # Plot trailing stop's price
            self.Plot("Data Chart", "Stop Price", self.stopMarketTicket.Get(OrderField.StopPrice))


    def OnData(self, data):
        if not self.sma.IsReady or self.spy not in data:
            return

        # List of daily highs, depending on the look back period (*12)
        self.high = self.History(self.spy, timedelta(self.lookback * 12), Resolution.Daily)["high"]
        self.low = self.History(self.spy, timedelta(self.lookback * 12), Resolution.Daily)["low"]

        #Plot d'un chart pour info
        self.Plot("Benchmark", "SMA", self.sma.Current.Value)

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status != OrderStatus.Filled:
            return
        
        if not self.Securities[self.spy].Invested:
            self.Log("SELL SPY @" + str(self.Securities[self.spy].Price))
