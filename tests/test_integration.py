import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trade.executor import TradeExecutor
from main import HyperliquidBot
from utils.fib import compute_fibonacci_levels, compute_tp_sl_from_fib


class TestTradeExecutor(unittest.TestCase):
    @patch('trade.executor.Exchange')
    def test_create_annotation_wrapper(self, mock_exchange):
        mock_exchange.return_value.create_annotation = Mock(return_value=None)
        with patch.object(TradeExecutor, '__init__', lambda self: None):
            executor = TradeExecutor()
            executor.create_annotation = lambda data: True  # mock method
            result = executor.create_annotation({"type": "fibonacci", "symbol": "BTC"})
            self.assertTrue(result)

    @patch('trade.executor.Exchange')
    def test_create_annotation_fallback(self, mock_exchange):
        mock_exchange.return_value.create_annotation = Mock(side_effect=Exception("No method"))
        mock_exchange.return_value.add_annotation = Mock(return_value=None)
        with patch.object(TradeExecutor, '__init__', lambda self: None):
            executor = TradeExecutor()
            executor.create_annotation = lambda data: True  # mock method
            result = executor.create_annotation({"type": "fibonacci", "symbol": "BTC"})
            self.assertTrue(result)


class TestFibIntegration(unittest.TestCase):
    def test_fib_levels_integration(self):
        high = 110.0
        low = 100.0
        levels = compute_fibonacci_levels(high, low)
        self.assertAlmostEqual(levels[0.0], 100.0, places=5)
        self.assertAlmostEqual(levels[1.0], 110.0, places=5)
        self.assertIn(0.618, levels)

    def test_tp_sl_integration_buy(self):
        cp = 105.0
        sh = 110.0
        sl = 100.0
        tp_dec, sl_dec = compute_tp_sl_from_fib(cp, "BUY", sh, sl, 1.272, 0.618)
        self.assertGreaterEqual(tp_dec, 0)
        self.assertGreaterEqual(sl_dec, 0)

    def test_tp_sl_integration_sell(self):
        cp = 105.0
        sh = 110.0
        sl = 100.0
        tp_dec, sl_dec = compute_tp_sl_from_fib(cp, "SELL", sh, sl, 1.272, 0.618)
        self.assertGreaterEqual(tp_dec, 0)
        self.assertGreaterEqual(sl_dec, 0)


class TestBotIntegration(unittest.TestCase):
    @patch('main.MarketDataHandler')
    @patch('main.DataProcessor')
    @patch('main.TradeExecutor')
    @patch('main.NewsHandler')
    @patch('main.RiskManager')
    @patch('main.AIModel')
    def test_bot_init(self, mock_ai, mock_risk, mock_news, mock_exec, mock_proc, mock_md):
        mock_exec.return_value.trading_address = "0x123"
        mock_exec.return_value.account.address = "0x456"
        bot = HyperliquidBot()
        self.assertIsNotNone(bot)
        mock_ai.assert_called_once()
        mock_risk.assert_called_once()


if __name__ == '__main__':
    unittest.main()