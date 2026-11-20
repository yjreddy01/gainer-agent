@echo off
REM Double-click to run the Top-Gainer agent (or schedule this file in Task Scheduler at 9:32 AM, Mon-Fri)
cd /d "%~dp0"
python gainer_agent.py --top 10
pause
