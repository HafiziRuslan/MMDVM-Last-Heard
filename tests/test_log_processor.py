#!/usr/bin/python3
"""
Test script to process MMDVM log files and display what would be sent to Telegram.
This script loads the MMDVMLogLine class from main.py and processes log entries.
"""

import os
import sys

# Mock telegram modules before importing main
import unittest.mock as mock

sys.modules['telegram'] = mock.MagicMock()
sys.modules['telegram.ext'] = mock.MagicMock()

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, src_dir)

# Now import from main.py
try:
	import importlib.util

	# Load main.py as a module
	main_path = os.path.join(src_dir, 'main.py')
	if not os.path.exists(main_path):
		main_path = os.path.join(project_root, 'main.py')
	spec = importlib.util.spec_from_file_location('main', main_path)
	main_module = importlib.util.module_from_spec(spec)

	# Inject required dependencies
	import asyncio
	import logging
	import threading

	main_module.threading = threading
	main_module.logging = logging
	main_module.os = os
	main_module.glob = __import__('glob')
	main_module.asyncio = asyncio
	main_module.load_dotenv = lambda: None  # Mock load_dotenv

	# Execute the module
	spec.loader.exec_module(main_module)

	# Import the class we need
	MMDVMLogLine = main_module.MMDVMLogLine
	RELEVANT_LOG_PATTERNS = main_module.RELEVANT_LOG_PATTERNS

	print('✅ Successfully loaded MMDVMLogLine class from main.py\n')

except Exception as e:
	print(f'❌ Error loading main.py: {e}')
	print(f'Make sure main.py is in {src_dir} or {project_root}.')
	sys.exit(1)


def run_unit_tests():
	"""Runs a series of predefined unit tests for log line parsing."""
	print('=' * 80)
	print('🔬 Running Unit Tests for Log Line Parsing')
	print('=' * 80)

	test_cases = [
		{
			'name': 'DMR Data Transmission (RF)',
			'log_line': 'M: 2026-03-04 10:20:30.123 DMR Slot 1, ended RF data transmission from 9W2ZDR to TG 50210, 15 blocks',
			'expected': {
				'mode': 'DMR-D',
				'callsign': '9W2ZDR',
				'destination': 'TG 50210',
				'is_voice': False,
				'is_network': False,
				'slot': 1,
				'block': 15,
				'data_type': 'data transmission',
			},
		},
		{
			'name': 'DMR Voice Transmission (RF)',
			'log_line': 'M: 2026-03-04 10:21:00.456 DMR Slot 2, received RF end of voice transmission from N0CALL to TG 9, 5.2 seconds, BER: 0.1%, RSSI: -110/-109/-111 dBm',
			'expected': {
				'mode': 'DMR',
				'callsign': 'N0CALL',
				'destination': 'TG 9',
				'is_voice': True,
				'is_network': False,
				'slot': 2,
				'duration': 5.2,
				'ber': 0.1,
				'rssi3': -111,
			},
		},
	]

	passed = 0
	failed = 0

	for test in test_cases:
		print(f'\n▶️  Testing: {test["name"]}')
		try:
			parsed = MMDVMLogLine.from_logline(test['log_line'])
			errors = []
			for key, value in test['expected'].items():
				if getattr(parsed, key) != value:
					errors.append(f'  - Mismatch on "{key}": Expected "{value}", Got "{getattr(parsed, key)}"')
			if not errors:
				print('  ✅ PASS')
				passed += 1
			else:
				print(f'  ❌ FAIL\n' + '\n'.join(errors))
				failed += 1
		except Exception as e:
			print(f'  ❌ FAIL: Exception during parsing: {e}')
			failed += 1

	print('\n' + '=' * 80)
	print(f'Test Results: {passed} passed, {failed} failed.')
	print('=' * 80)
	sys.exit(failed)


def process_log_file(log_file_path: str, ignore_time_messages: bool = True):
	"""
	Process a log file and display all entries that would be sent to Telegram.

	Args:
	        log_file_path: Path to the MMDVM log file
	        ignore_time_messages: Whether to ignore /TIME messages (default: True)
	"""

	# Patterns to match (same as in main.py)
	relevant_patterns = RELEVANT_LOG_PATTERNS

	print('=' * 80)
	print(f'Processing log file: {log_file_path}')
	print('=' * 80)
	print()

	if not os.path.exists(log_file_path):
		print(f'❌ Error: File not found: {log_file_path}')
		return

	total_lines = 0
	matched_lines = 0
	parsed_entries = 0
	telegram_messages = 0
	last_timestamp = None

	entries = []

	try:
		with open(log_file_path, 'r', encoding='UTF-8', errors='replace') as f:
			for line_num, line in enumerate(f, 1):
				total_lines += 1
				line = line.strip()

				# Skip empty lines
				if not line or len(line) < 10:
					continue

				# Check if line matches our patterns
				if not any(pattern in line.lower() for pattern in relevant_patterns):
					continue

				matched_lines += 1

				try:
					# Parse the log line
					parsed = MMDVMLogLine.from_logline(line)
					parsed_entries += 1

					# Check if this is a duplicate timestamp (same as last processed)
					if last_timestamp and parsed.timestamp <= last_timestamp:
						continue

					last_timestamp = parsed.timestamp

					# Check if we should ignore this message
					if ignore_time_messages and '/TIME' in parsed.callsign:
						continue

					# Get the Telegram message
					tg_message = parsed.get_telegram_message()

					if tg_message:
						telegram_messages += 1
						entries.append({'line_num': line_num, 'parsed': parsed, 'message': tg_message})

				except ValueError:
					# Line didn't match any pattern
					pass
				except Exception as e:
					print(f'⚠️ Warning at line {line_num}: {e}')

	except Exception as e:
		print(f'❌ Error reading file: {e}')
		return

	# Display statistics
	print('📊 Statistics:')
	print(f'  Total lines in file: {total_lines}')
	print(f'  Lines matching patterns: {matched_lines}')
	print(f'  Successfully parsed entries: {parsed_entries}')
	print(f'  Messages for Telegram: {telegram_messages}')
	print()

	if telegram_messages == 0:
		print('ℹ️ No messages would be sent to Telegram from this log file.')
		return

	# Display all messages
	print('=' * 80)
	print(f'📱 TELEGRAM MESSAGES ({telegram_messages} total)')
	print('=' * 80)
	print()

	for idx, entry in enumerate(entries, 1):
		print(f'{"─" * 80}')
		print(f'Message #{idx} (from line {entry["line_num"]})')
		print(f'{"─" * 80}')

		parsed = entry['parsed']
		print(f'📍 Mode: {parsed.mode}')
		print(f'📍 Callsign: {parsed.callsign}')
		print(f'📍 Destination: {parsed.destination}')
		print(f'📍 Timestamp: {parsed.timestamp}')
		print(f'📍 Network: {"Yes" if parsed.is_network else "No (RF)"}')
		print()
		print('Telegram Message (HTML format):')
		print('┌' + '─' * 78 + '┐')
		for line in entry['message'].split('\n'):
			print(f'│ {line:<76} │')
		print('└' + '─' * 78 + '┘')
		print()

	print('=' * 80)
	print('✅ Processing complete!')
	print('=' * 80)


def main():
	"""Main function"""
	import argparse

	parser = argparse.ArgumentParser(
		description='Test MMDVM log processing and display Telegram messages',
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""Examples:
  # Process a specific log file
  %(prog)s MMDVM-2026-01-01.log

  # Process a log file and include /TIME messages
  %(prog)s MMDVM-2026-01-01.log --include-time

  # Run built-in unit tests for the log line parser
  %(prog)s --test
		""",
	)

	parser.add_argument('logfile', nargs='?', default=None, help='Path to the MMDVM log file to process. If not provided, must use --test.')
	parser.add_argument('--include-time', action='store_true', help='Include /TIME messages (by default they are ignored)')
	parser.add_argument('--test', action='store_true', help='Run built-in unit tests for log line parsing.')

	args = parser.parse_args()

	if args.test:
		run_unit_tests()
	elif args.logfile:
		process_log_file(args.logfile, ignore_time_messages=not args.include_time)
	else:
		parser.print_help()
		sys.exit(1)


if __name__ == '__main__':
	main()
