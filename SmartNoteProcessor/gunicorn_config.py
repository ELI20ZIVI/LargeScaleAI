import os
import multiprocessing

bind = "0.0.0.0:5000"
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 120  # Increased timeout to handle longer API calls
keepalive = 5
worker_class = "sync"
reload = True
reuse_port = True
accesslog = "-"
errorlog = "-"
loglevel = "info"