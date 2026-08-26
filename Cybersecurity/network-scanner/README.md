# Network Scanner

A bounded TCP scanner for explicitly authorized hosts. Run `python main.py 127.0.0.1 --ports 22,80,443`.

The implementation uses socket timeouts and does not expand beyond the host and ports supplied by the operator.
