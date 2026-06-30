# legacy_analytics.py (Target Source: Python 2.7 compliant)
import csv

def process_historical_logs(file_path, downsample_rate):
    print "Beginning log processing for:", file_path
    stride = downsample_rate / 2
    with open(file_path, 'rb') as f:
        reader = csv.reader(f)
        records = [row for row in reader]
    log_data = map(lambda r: r, records[::stride])
    log_data.reverse()
    return log_data
