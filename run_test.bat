@echo off
poetry run python test_dbs.py > result_dbs.txt 2>&1
echo Done >> result_dbs.txt
