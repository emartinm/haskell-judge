# gunicorn configuration of the Haskell judge (see deploy/haskell-judge.service.example)
import os

# Local address where the reverse proxy forwards /haskell/ (GUNICORN_BIND in the env file)
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# Threads: a submission waits for the executor (up to a few seconds if there is a queue)
# and keeps a thread busy, not a whole process, so the rest of the pages keep answering.
worker_class = "gthread"
workers = 2
threads = 8

# A submission may wait in the executor queue in a peak of load
timeout = 120

# Logs to stdout/stderr: they end up in the systemd journal
accesslog = "-"
errorlog = "-"
capture_output = True
loglevel = "info"
