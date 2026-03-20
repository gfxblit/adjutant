import unittest
from unittest.mock import patch, MagicMock
import time
from adjutant.ui import run_ui

class TestRunUI(unittest.TestCase):
    @patch("adjutant.ui.AdjutantHUD")
    @patch("time.sleep")
    def test_run_ui_basic(self, mock_sleep, mock_hud_class):
        mock_hud_instance = mock_hud_class.return_value
        
        # Make sleep raise an exception to exit the loop
        mock_sleep.side_effect = KeyboardInterrupt
        
        with patch("builtins.print") as mock_print:
            run_ui("Test Mission")
        
        mock_hud_class.assert_called_once_with(mission="Test Mission")
        mock_hud_instance.start.assert_called_once()
        mock_hud_instance.stop.assert_called_once()
        mock_print.assert_any_call("\n[Adjutant HUD: Shutting Down]")

if __name__ == "__main__":
    unittest.main()
