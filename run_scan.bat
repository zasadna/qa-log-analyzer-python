@echo off

echo ============================================
echo        QA Log Analyzer - Python Tool
echo ============================================
echo.

echo This tool will scan log files and search for common issue indicators
echo such as errors, warnings, timeouts, and other potential problems.
echo.

echo Step 1: Starting log analysis...
echo.

python scan_logs.py

echo.
echo ============================================
echo Analysis finished.
echo.
echo Reports have been generated in the "reports" folder.
echo You can open the CSV files there to review the results.
echo.
echo Press any key to close this window.
echo ============================================

pause