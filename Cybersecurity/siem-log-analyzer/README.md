# SIEM Log Analyzer

Parses failed-login lines, correlates user and source IP, and flags counts at or above a configurable threshold.

Run `python main.py sample.log --threshold 3`. Input is read-only and the result is printed as structured data.
