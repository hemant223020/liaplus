#!/usr/bin/env python3
"""
Log Analyzer Script

This script analyzes web server logs (Nginx/Apache) to provide insights on:
- Traffic patterns
- Error rates
- Performance metrics
- Security issues
- Bot traffic

Usage:
    python log_analyzer.py --file <log_file> [--format nginx|apache] [--report full|summary]
    python log_analyzer.py --dir <log_directory> [--pattern "*.log"] [--format nginx|apache]
"""

import os
import re
import sys
import gzip
import json
import argparse
import datetime
from collections import Counter, defaultdict
from pathlib import Path
import ipaddress
import matplotlib.pyplot as plt


# Regular expressions for different log formats
LOG_PATTERNS = {
    'nginx': re.compile(
        r'(?P<ip>\d+\.\d+\.\d+\.\d+) - (?P<user>.?) \[(?P<datetime>.?)\] "(?P<method>\w+) (?P<path>.*?) HTTP/\d\.\d" '
        r'(?P<status>\d+) (?P<size>\d+) "(?P<referrer>.?)" "(?P<agent>.?)"'
    ),
    'apache': re.compile(
        r'(?P<ip>\d+\.\d+\.\d+\.\d+) - (?P<user>.?) \[(?P<datetime>.?)\] "(?P<method>\w+) (?P<path>.*?) HTTP/\d\.\d" '
        r'(?P<status>\d+) (?P<size>\d+)(?: "(?P<referrer>.?)" "(?P<agent>.?)")?'
    )
}

# Define common bots for detection
BOTS = [
    'googlebot', 'bingbot', 'yandexbot', 'ahrefsbot', 'msnbot', 'baiduspider',
    'facebookexternalhit', 'twitterbot', 'rogerbot', 'linkedinbot', 'embedly',
    'quora link preview', 'showyoubot', 'outbrain', 'pinterest', 'slackbot',
    'vkshare', 'w3c_validator', 'crawler', 'spider', 'bot'
]

# Define security threat patterns
SECURITY_THREATS = [
    r'(\'|\%27)(\s|\+|\/|\%20)*((\%6F)|o|(\%4F))((\%72)|r|(\%52))',  # SQL injection
    r'((\%3C)|<)((\%2F)|\/)*[a-z0-9\%]+((\%3E)|>)',  # XSS
    r'\.\.(\%2F|\/)',  # Path traversal
    r'etc(\%2F|\/)passwd',  # /etc/passwd access
    r'((\%27)|\'|(\%22)|\").*?(((\%6F)|o|(\%4F))((\%72)|r|(\%52)))',  # More SQL injection
]


class LogAnalyzer:
    def _init_(self, log_format='nginx'):
        self.log_format = log_format
        self.pattern = LOG_PATTERNS[log_format]
        self.logs = []
        self.ip_counts = Counter()
        self.status_counts = Counter()
        self.path_counts = Counter()
        self.method_counts = Counter()
        self.user_agent_counts = Counter()
        self.hourly_traffic = defaultdict(int)
        self.daily_traffic = defaultdict(int)
        self.errors = []
        self.slow_requests = []
        self.potential_attacks = []
        self.bot_requests = []
        self.total_bytes = 0
        self.request_times = []  # If log contains request times

    def parse_log_file(self, log_file):
        """Parse a single log file."""
        print(f"Parsing log file: {log_file}")
        
        # Determine if file is gzipped
        opener = gzip.open if str(log_file).endswith('.gz') else open
        
        with opener(log_file, 'rt', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    match = self.pattern.match(line.strip())
                    if match:
                        log_entry = match.groupdict()
                        
                        # Process timestamp
                        try:
                            timestamp_str = log_entry['datetime']
                            # Example: 01/Jul/2023:12:34:56 +0000
                            timestamp = datetime.datetime.strptime(
                                timestamp_str.split()[0], "%d/%b/%Y:%H:%M:%S"
                            )
                            log_entry['timestamp'] = timestamp
                            self.hourly_traffic[timestamp.strftime("%Y-%m-%d %H:00")] += 1
                            self.daily_traffic[timestamp.strftime("%Y-%m-%d")] += 1
                        except ValueError:
                            log_entry['timestamp'] = None
                        
                        # Process status code
                        status = int(log_entry['status'])
                        self.status_counts[status] += 1
                        
                        # Collect error information
                        if status >= 400:
                            self.errors.append({
                                'line': line_num,
                                'status': status,
                                'path': log_entry['path'],
                                'ip': log_entry['ip'],
                                'timestamp': log_entry.get('timestamp')
                            })
                        
                        # Process request size
                        try:
                            size = int(log_entry['size'])
                            self.total_bytes += size
                            
                            # Identify potentially slow requests (large response size)
                            if size > 1000000:  # Greater than 1MB
                                self.slow_requests.append({
                                    'line': line_num,
                                    'path': log_entry['path'],
                                    'size': size,
                                    'timestamp': log_entry.get('timestamp')
                                })
                        except ValueError:
                            pass
                        
                        # Count IPs, paths, methods
                        self.ip_counts[log_entry['ip']] += 1
                        self.path_counts[log_entry['path']] += 1
                        self.method_counts[log_entry['method']] += 1
                        
                        # Process user agent
                        user_agent = log_entry.get('agent', '').lower()
                        self.user_agent_counts[user_agent] += 1
                        
                        # Check for bot traffic
                        if any(bot in user_agent for bot in BOTS):
                            self.bot_requests.append({
                                'line': line_num,
                                'ip': log_entry['ip'],
                                'agent': log_entry.get('agent'),
                                'path': log_entry['path']
                            })
                        
                        # Check for security threats
                        path = log_entry['path']
                        for pattern in SECURITY_THREATS:
                            if re.search(pattern, path, re.IGNORECASE):
                                self.potential_attacks.append({
                                    'line': line_num,
                                    'ip': log_entry['ip'],
                                    'path': path,
                                    'pattern': pattern,
                                    'timestamp': log_entry.get('timestamp')
                                })
                                break
                        
                        self.logs.append(log_entry)
                    else:
                        print(f"Warning: Could not parse line {line_num}: {line[:50]}...")
                except Exception as e:
                    print(f"Error processing line {line_num}: {e}")

    def parse_log_directory(self, directory, pattern=".log"):
        """Parse all log files in a directory matching the pattern."""
        directory_path = Path(directory)
        for log_file in directory_path.glob(pattern):
            self.parse_log_file(log_file)

    def generate_summary(self):
        """Generate a summary of log analysis results."""
        summary = {
            "total_requests": len(self.logs),
            "unique_ips": len(self.ip_counts),
            "total_bytes_transferred": self.total_bytes,
            "average_bytes_per_request": self.total_bytes / len(self.logs) if self.logs else 0,
            "status_code_distribution": dict(self.status_counts),
            "http_method_distribution": dict(self.method_counts),
            "top_10_paths": dict(self.path_counts.most_common(10)),
            "top_10_ips": dict(self.ip_counts.most_common(10)),
            "error_count": len(self.errors),
            "bot_request_count": len(self.bot_requests),
            "potential_security_threats": len(self.potential_attacks),
            "slow_requests": len(self.slow_requests)
        }
        return summary

    def generate_full_report(self):
        """Generate a detailed report with all collected data."""
        report = self.generate_summary()
        report.update({
            "hourly_traffic": dict(self.hourly_traffic),
            "daily_traffic": dict(self.daily_traffic),
            "errors": self.errors[:100],  # Limit to first 100 errors
            "bot_requests": self.bot_requests[:100],  # Limit to first 100 bot requests
            "potential_attacks": self.potential_attacks,
            "slow_requests": self.slow_requests,
            "top_user_agents": dict(self.user_agent_counts.most_common(20))
        })
        return report

    def generate_traffic_graph(self, output_file="traffic_graph.png"):
        """Generate a graph showing traffic patterns."""
        if not self.hourly_traffic:
            print("No traffic data available for graph")
            return
        
        # Sort hourly traffic by timestamp
        sorted_traffic = sorted(self.hourly_traffic.items())
        timestamps = [item[0] for item in sorted_traffic]
        counts = [item[1] for item in sorted_traffic]
        
        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, counts)
        plt.title("Hourly Traffic")
        plt.xlabel("Hour")
        plt.ylabel("Requests")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(output_file)
        plt.close()
        
        print(f"Traffic graph saved to {output_file}")

    def detect_anomalies(self):
        """Detect potential anomalies in the logs."""
        anomalies = []
        
        # Detect unusual traffic spikes
        if self.hourly_traffic:
            values = list(self.hourly_traffic.values())
            avg_traffic = sum(values) / len(values)
            std_dev = (sum((x - avg_traffic) ** 2 for x in values) / len(values)) ** 0.5
            
            for hour, count in self.hourly_traffic.items():
                if count > avg_traffic + 3 * std_dev:
                    anomalies.append({
                        "type": "traffic_spike",
                        "hour": hour,
                        "count": count,
                        "avg_traffic": avg_traffic,
                        "deviation": (count - avg_traffic) / std_dev if std_dev else 0
                    })
        
        # Detect IPs with unusually high request counts
        if self.ip_counts:
            ips = list(self.ip_counts.items())
            if ips:
                values = [count for _, count in ips]
                avg_requests = sum(values) / len(values)
                std_dev = (sum((x - avg_requests) ** 2 for x in values) / len(values)) ** 0.5
                
                for ip, count in ips:
                    if count > avg_requests + 3 * std_dev and count > 100:
                        anomalies.append({
                            "type": "unusual_ip_activity",
                            "ip": ip,
                            "count": count,
                            "avg_requests": avg_requests,
                            "deviation": (count - avg_requests) / std_dev if std_dev else 0
                        })
        
        # Detect unusually high error rates
        error_rate = len(self.errors) / len(self.logs) if self.logs else 0
        if error_rate > 0.05:  # More than 5% errors
            anomalies.append({
                "type": "high_error_rate",
                "error_rate": error_rate,
                "error_count": len(self.errors),
                "total_requests": len(self.logs)
            })
        
        return anomalies


def main():
    parser = argparse.ArgumentParser(description="Analyze web server log files")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to the log file")
    group.add_argument("--dir", help="Path to directory containing log files")
    parser.add_argument("--pattern", default=".log", help="Pattern for log files when using --dir")
    parser.add_argument("--format", choices=["nginx", "apache"], default="nginx", help="Log file format")
    parser.add_argument("--report", choices=["summary", "full"], default="summary", help="Report type")
    parser.add_argument("--output", default="log_analysis_report.json", help="Output file for the report")
    parser.add_argument("--graph", action="store_true", help="Generate traffic graph")
    args = parser.parse_args()

    analyzer = LogAnalyzer(log_format=args.format)
    
    try:
        if args.file:
            analyzer.parse_log_file(args.file)
        elif args.dir:
            analyzer.parse_log_directory(args.dir, pattern=args.pattern)
        
        if not analyzer.logs:
            print("No log entries were found or parsed successfully")
            return 1
            
        print(f"Parsed {len(analyzer.logs)} log entries")
        
        # Generate appropriate report
        if args.report == "summary":
            report = analyzer.generate_summary()
        else:
            report = analyzer.generate_full_report()
        
        # Detect anomalies
        anomalies = analyzer.detect_anomalies()
        if anomalies:
            report["anomalies"] = anomalies
            print(f"Found {len(anomalies)} potential anomalies")
        
        # Save report to file
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2, default=str)
            
        print(f"Report saved to {args.output}")
        
        # Generate traffic graph if requested
        if args.graph:
            analyzer.generate_traffic_graph()
        
        # Print summary to console
        print("\nSummary:")
        print(f"Total Requests: {report['total_requests']}")
        print(f"Unique IPs: {report['unique_ips']}")
        print(f"Total Data Transferred: {report['total_bytes_transferred'] / (1024*1024):.2f} MB")
        print(f"Error Rate: {len(analyzer.errors) / len(analyzer.logs) * 100:.2f}%")
        print(f"Bot Traffic: {len(analyzer.bot_requests) / len(analyzer.logs) * 100:.2f}%")
        print(f"Potential Security Threats: {len(analyzer.potential_attacks)}")
        
        if anomalies:
            print("\nPotential Anomalies Detected:")
            for anomaly in anomalies:
                if anomaly["type"] == "traffic_spike":
                    print(f"  Traffic spike at {anomaly['hour']}: {anomaly['count']} requests "
                          f"({anomaly['deviation']:.2f} std devs above average)")
                elif anomaly["type"] == "unusual_ip_activity":
                    print(f"  Unusual activity from IP {anomaly['ip']}: {anomaly['count']} requests "
                          f"({anomaly['deviation']:.2f} std devs above average)")
                elif anomaly["type"] == "high_error_rate":
                    print(f"  High error rate: {anomaly['error_rate']*100:.2f}% ({anomaly['error_count']} errors)")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if _name_ == "_main_":
    sys.exit(main())