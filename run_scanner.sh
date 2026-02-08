#!/bin/bash

# Eagle Eye Scanner Cron Job
# This script activates the virtual environment and runs the scanner

cd /Users/vivekjoshi/SAAS/CupAndHandle-main
source .venv/bin/activate
python scanner_job.py >> logs/scanner_$(date +\%Y\%m\%d).log 2>&1
