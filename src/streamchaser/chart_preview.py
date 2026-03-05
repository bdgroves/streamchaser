"""chart_preview.py — invoked by `pixi run chart` for visual testing."""
from streamchaser.chart import __name__ as _
# chart.py __main__ block handles it when run directly
import runpy
runpy.run_module("streamchaser.chart", run_name="__main__", alter_sys=True)
