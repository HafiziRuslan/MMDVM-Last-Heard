#!/usr/bin/python3
"""MMDVM LastHeard - Telegram bot to monitor the last transmissions of a MMDVM gateway"""

import asyncio
import configparser
import datetime as dt
import difflib
import glob
import logging
import logging.handlers
import os
import re
import shutil
import signal
import subprocess
import tomllib
from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
from typing import Optional

import humanize
from dotenv import load_dotenv
from codes import COUNTRY_CODES, MCC_CODES
from telegram.ext import Application as TelegramApplication
from telegram.ext import ApplicationBuilder


@lru_cache
def _get_app_metadata():
	repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	git_sha = ''
	if shutil.which('git'):
		try:
			git_sha = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD^'], cwd=repo_path).decode('ascii').strip()
		except Exception:
			pass
	meta = {'name': 'MMDVM_LastHeard', 'version': '0.1', 'github': 'https://git.new/mmdvmlhbot'}
	try:
		with open(os.path.join(repo_path, 'pyproject.toml'), 'rb') as f:
			data = tomllib.load(f).get('project', {})
			meta.update({k: data.get(k, meta[k]) for k in ['name', 'version']})
			meta['github'] = data.get('urls', {}).get('github', meta['github'])
	except Exception as e:
		logging.warning('Failed to load project metadata: %s', e)
	return f'{"-".join(filter(None, [meta["name"], meta["version"], git_sha]))}', meta['github']


class ConfigManager:
	"""Manages all application configuration."""

	def __init__(self):
		load_dotenv()
		self.tg_bot_token = os.getenv('TG_BOTTOKEN', '')
		self.tg_chat_id = os.getenv('TG_CHATID', '')
		self.tg_topic_id = os.getenv('TG_TOPICID', '0')
		self.gw_ignore_time_messages = os.getenv('GW_IGNORE_MESSAGES', 'True').lower() == 'true'

		# Map numeric LOG_LEVEL from environment variable
		# [0: off, 1: debug, 2: info, 3: warning, 4: error, 5: critical]
		log_level_map = {
			0: logging.CRITICAL + 1,  # Effectively 'off' by setting level higher than CRITICAL
			1: logging.DEBUG,
			2: logging.INFO,
			3: logging.WARNING,
			4: logging.ERROR,
			5: logging.CRITICAL,
		}

		log_level_raw = os.getenv('LOG_LEVEL')
		try:
			log_level_int = int(log_level_raw)
			self.log_level = log_level_map.get(log_level_int, logging.INFO)
		except (TypeError, ValueError):
			# Fallback to INFO if LOG_LEVEL is not set or not a valid integer
			logging.warning('LOG_LEVEL environment variable must be an integer between 0 and 5. Defaulting to INFO.')
			self.log_level = logging.INFO

		# Parse LOG_MAX_SIZE and LOG_MAX_COUNT as integers, providing string defaults
		self.log_max_size_mb = int(os.getenv('LOG_MAX_SIZE', '1'))  # Default 1MB
		self.log_max_count = int(os.getenv('LOG_MAX_COUNT', '3'))  # Default 3 backups

		self.app_name, self.project_url = _get_app_metadata()
		self.app_name_short = self.app_name.split('-')[0]

		self.relevant_log_patterns = ['end of voice transmission', 'end of transmission', 'watchdog has expired']

		if not self.tg_bot_token or not self.tg_chat_id:
			logging.warning('TG_BOTTOKEN or TG_CHATID is not set in the environment variables.')
		if self.gw_ignore_time_messages:
			logging.info('GW_IGNORE_MESSAGES is set to true, messages from the gateway will be ignored.')


class LoggingManager:
	"""Manages the application's logging configuration."""

	class ISO8601Formatter(logging.Formatter):
		"""A logging formatter that uses ISO 8601 format for timestamps."""

		def formatTime(self, record, datefmt=None):
			return dt.datetime.fromtimestamp(record.created, dt.timezone.utc).astimezone().isoformat(timespec='milliseconds')

	class NumberedRotatingFileHandler(logging.handlers.RotatingFileHandler):
		"""RotatingFileHandler with backup number before the extension."""

		def doRollover(self):
			"""Do a rollover, with numbering before the extension."""
			if self.stream:
				self.stream.close()
				self.stream = None
			if self.backupCount > 0:
				name, ext = os.path.splitext(self.baseFilename)
				for i in range(self.backupCount - 1, 0, -1):
					sfn = self.rotation_filename(f'{name}{i}{ext}')
					dfn = self.rotation_filename(f'{name}{i + 1}{ext}')
					if os.path.exists(sfn):
						if os.path.exists(dfn):
							os.remove(dfn)
						os.rename(sfn, dfn)
				dfn = self.rotation_filename(f'{name}1{ext}')
				if os.path.exists(dfn):
					os.remove(dfn)
				self.rotate(self.baseFilename, dfn)
			if not self.delay:
				self.stream = self._open()

	class LevelFilter(logging.Filter):
		"""A filter that allows log records of a specific level."""

		def __init__(self, level):
			self.level = level

		def filter(self, record):
			return record.levelno == self.level

	def __init__(
		self,
		log_dir: str = '/var/log/mmdvmlhbot',
		fallback_log_dir: str = 'logs',
		log_level: int = logging.INFO,
		log_max_size_mb: int = 1,
		log_max_count: int = 3,
	):
		self.log_dir = log_dir
		if not os.path.exists(self.log_dir) or not os.access(self.log_dir, os.W_OK):
			self.log_dir = fallback_log_dir
		if not os.path.exists(self.log_dir):
			os.makedirs(self.log_dir)
		self.log_level = log_level
		self.log_max_size_bytes = log_max_size_mb * 1024 * 1024
		self.log_max_count = log_max_count
		self._formatter = self.ISO8601Formatter('%(asctime)s | %(levelname)-8s | %(threadName)-12s | %(name)s.%(funcName)s:%(lineno)d | %(message)s')

	def setup(self):
		"""Sets up the logging configuration."""
		self._set_library_log_levels()
		logger = logging.getLogger()
		logger.setLevel(self.log_level)
		self._configure_console_handler(logger)
		self._configure_file_handlers(logger)

	def _set_library_log_levels(self):
		"""Sets specific log levels for external libraries."""
		external_libs = ['asyncio', 'hpack', 'httpx', 'telegram', 'urllib3']
		for lib in external_libs:
			logging.getLogger(lib).setLevel(self.log_level)

	def _configure_console_handler(self, logger: logging.Logger):
		"""Configures and adds the console log handler."""
		console_handler = logging.StreamHandler()
		console_handler.setLevel(logging.WARNING)  # Console handler still shows WARNING by default
		console_handler.setFormatter(self._formatter)
		logger.addHandler(console_handler)

	def _configure_file_handlers(self, logger: logging.Logger):
		"""Configures and adds rotating file handlers for different log levels."""
		levels_map = {
			logging.DEBUG: '1-debug.log',
			logging.INFO: '2-info.log',
			logging.WARNING: '3-warning.log',
			logging.ERROR: '4-error.log',
			logging.CRITICAL: '5-critical.log',
		}
		for level, filename in levels_map.items():
			# Only create handlers for levels at or above the configured log_level
			if level >= self.log_level:
				try:
					handler = self.NumberedRotatingFileHandler(
						os.path.join(self.log_dir, filename), maxBytes=self.log_max_size_bytes, backupCount=self.log_max_count
					)
					handler.setLevel(level)
					handler.addFilter(self.LevelFilter(level))
					handler.setFormatter(self._formatter)
					logger.addHandler(handler)
				except (OSError, PermissionError) as e:
					logging.error('Failed to create %s: %s', filename, e)


class Formatter:
	"""A collection of formatting utility functions."""

	@staticmethod
	def remove_double_spaces(text: str) -> str:
		"""Removes double spaces from a string."""
		while '  ' in text:
			text = text.replace('  ', ' ')
		return text

	@staticmethod
	@lru_cache(maxsize=128)
	def get_country_code(country_name: str) -> str:
		"""Returns the country code for a given country name."""
		code = COUNTRY_CODES.get(country_name)
		if not code:
			for name, c in COUNTRY_CODES.items():
				if name.lower() == country_name.lower():
					code = c
					break
			if not code:
				matches = difflib.get_close_matches(country_name, COUNTRY_CODES.keys(), n=1, cutoff=0.8)
				if matches:
					code = COUNTRY_CODES[matches[0]]
		return code if code else ''

	@staticmethod
	def get_flag_emoji(country_code: str) -> str:
		"""Converts a two-letter country code to a flag emoji."""
		if country_code and len(country_code) == 2:
			return ''.join(chr(ord(c) + 127397) for c in country_code.upper())
		return '🌐'


class DMRGatewayManager:
	"""Manages loading and caching of DMRGateway configuration."""

	def __init__(self, config_files: list[str] = None):
		self._cache = {'path': None, 'mtime': 0, 'rules': [], 'networks': []}
		self._conf_files = config_files or ['/etc/dmrgateway', '/etc/DMRGateway.ini', '/opt/DMRGateway/DMRGateway.ini']

	def get_rules(self) -> list:
		"""Returns the list of rewrite rules."""
		self._update_cache()
		return self._cache['rules']

	def get_networks(self) -> list:
		"""Returns the list of configured networks."""
		self._update_cache()
		return self._cache['networks']

	def _update_cache(self):
		"""Updates the cache if the configuration file has changed."""
		config_path = self._cache['path']
		if not config_path or not os.path.isfile(config_path):
			config_path = None
			for f in self._conf_files:
				if os.path.isfile(f):
					config_path = f
					break
		if config_path:
			try:
				mtime = os.path.getmtime(config_path)
				if config_path == self._cache['path'] and mtime == self._cache['mtime']:
					return
				rules = []
				networks = []
				config = configparser.ConfigParser(strict=False, interpolation=None)
				config.read(config_path)
				for section in config.sections():
					if section.startswith('DMR Network'):
						net_name = config.get(section, 'Name', fallback=section)
						networks.append(net_name)
						for key, value in config.items(section):
							key_lower = key.lower()
							rule_type = None
							if key_lower.startswith('tgrewrite'):
								rule_type = 'TG'
							elif key_lower.startswith('pcrewrite'):
								rule_type = 'PC'
							if rule_type:
								parts = [p.strip() for p in value.split(',')]
								if len(parts) >= 5:
									try:
										src_slot = int(parts[0])
										src_tg = int(parts[1])
										dst_tg = int(parts[3])
										range_val = int(parts[4])
										rules.append(
											{
												'slot': src_slot,
												'start': src_tg,
												'end': src_tg + range_val - 1,
												'offset': dst_tg - src_tg,
												'name': net_name,
												'type': rule_type,
											}
										)
									except ValueError:
										continue
				self._cache = {'path': config_path, 'mtime': mtime, 'rules': rules, 'networks': networks}
			except Exception as e:
				logging.error('Error reading DMRGateway config %s: %s', config_path, e)


class TalkgroupManager:
	"""Manages loading, caching, and retrieving talkgroup information."""

	def __init__(self, dmr_gateway_manager: DMRGatewayManager):
		"""Initializes the TalkgroupManager."""
		self._dmr_gateway_manager = dmr_gateway_manager
		self._cache = {'mtimes': {}, 'tg_map': {}}

	def get_map(self) -> dict:
		"""Reads and caches the talkgroup list from files, reloading if files change."""
		current_mtimes, expanded_configs, catch_all_files = self._collect_files_and_mtimes()
		if current_mtimes == self._cache.get('mtimes') and self._cache.get('tg_map'):
			return self._cache['tg_map']
		tg_map = {}
		processed_files = set()
		for files, delimiter, id_idx, name_idx in expanded_configs:
			for tg_file in files:
				processed_files.add(tg_file)
				filename = os.path.basename(tg_file)
				name_part = os.path.splitext(filename)[0]
				suffix = name_part[7:] if name_part.startswith('TGList_') else name_part
				self._read_talkgroup_file(tg_file, delimiter, id_idx, name_idx, tg_map, suffix=suffix, overwrite=True)
		for tg_file in catch_all_files:
			if tg_file not in processed_files:
				filename = os.path.basename(tg_file)
				name_part = os.path.splitext(filename)[0]
				suffix = name_part[7:] if name_part.startswith('TGList_') else name_part
				self._read_talkgroup_file(tg_file, ';', 0, 1, tg_map, suffix=suffix, overwrite=False)
		self._apply_special_rules(tg_map)
		self._cache = {'mtimes': current_mtimes, 'tg_map': tg_map}
		return tg_map

	def _read_talkgroup_file(
		self, file_path: str, delimiter: str, id_idx: int, name_idx: int, tg_map: dict, suffix: str = '', overwrite: bool = True
	):
		"""Helper to read a talkgroup file and update the map."""
		if not os.path.isfile(file_path):
			return
		try:
			with open(file_path, 'r', encoding='UTF-8', errors='replace') as file:
				for line in file:
					line = line.strip()
					if line.startswith('#') or not line:
						continue
					parts = line.split(maxsplit=1) if delimiter == ' ' else line.split(delimiter)
					try:
						if len(parts) > max(id_idx, name_idx):
							tgid = parts[id_idx].strip()
							name = parts[name_idx].strip()
							if tgid and name:
								display_name = f'{suffix}: {name}' if suffix else name
								if overwrite or tgid not in tg_map:
									tg_map[tgid] = display_name
					except IndexError:
						continue
		except Exception as e:
			logging.error('Error reading talkgroup file %s: %s', file_path, e)

	def _get_static_sources(self) -> list[tuple[str, str, int, int]]:
		"""Returns the list of static talkgroup file sources."""
		return [
			('/usr/local/etc/groups.txt', ':', 0, 1),
			('/usr/local/etc/groupsNextion.txt', ',', 0, 1),
			('/usr/local/etc/TGList_ADN', ',', 0, 1),
			('/usr/local/etc/TGList_ADN-NoPrefix', ',', 0, 1),
			('/usr/local/etc/TGList_BM', ';', 0, 2),
			('/usr/local/etc/TGList_DMRp', ',', 0, 1),
			('/usr/local/etc/TGList_DMRp_NoPrefix', ',', 0, 1),
			('/usr/local/etc/TGList_FreeDMR', ',', 0, 1),
			('/usr/local/etc/TGList_FreeStarIPSC', ',', 0, 1),
			('/usr/local/etc/TGList_NXDN', ';', 0, 2),
			('/usr/local/etc/TGList_P25', ';', 0, 2),
			('/usr/local/etc/TGList_QuadNet', ',', 0, 1),
			('/usr/local/etc/TGList_QuadNet-NoPrefix', ',', 0, 1),
			('/usr/local/etc/TGList_SystemX', ',', 0, 1),
			('/usr/local/etc/TGList_TGIF', ';', 0, 1),
			('/usr/local/etc/TGList_YSF', ';', 0, 1),
		]

	def _get_dynamic_sources(self) -> list[tuple[str, str, int, int]]:
		"""Returns the list of dynamic talkgroup file sources based on DMRGateway config."""
		configs = []
		for net in self._dmr_gateway_manager.get_networks():
			name_clean = net.split('_')[0]
			fpath = f'/usr/local/etc/TGList_{name_clean}.txt'
			name_idx = 2 if 'BM' in name_clean else 1
			configs.append((fpath, ';', 0, name_idx))
		return configs

	def _collect_files_and_mtimes(self) -> tuple[dict, list, list]:
		"""Collects all talkgroup files and their modification times."""
		mtimes = {}
		expanded_configs = []
		sources = self._get_static_sources() + self._get_dynamic_sources()
		for pattern, delimiter, id_idx, name_idx in sources:
			files = glob.glob(pattern)
			expanded_configs.append((files, delimiter, id_idx, name_idx))
			for f in files:
				try:
					mtimes[f] = os.path.getmtime(f)
				except OSError:
					pass
		catch_all_files = glob.glob('/usr/local/etc/TGList_*.txt')
		for f in catch_all_files:
			try:
				mtimes[f] = os.path.getmtime(f)
			except OSError:
				pass
		return mtimes, expanded_configs, catch_all_files

	def _apply_special_rules(self, tg_map: dict):
		"""Applies special talkgroup rules for DMRGateway and MCCs."""
		for rule in self._dmr_gateway_manager.get_rules():
			if rule.get('type') in ('TG', 'PC'):
				for target_tg, label in [(4000, 'Disconnect'), (9990, 'Parrot'), (31000, 'Parrot')]:
					src_tg = target_tg - rule['offset']
					if rule['start'] <= src_tg <= rule['end']:
						tg_map[str(src_tg)] = label
		for mcc, (country, _) in MCC_CODES.items():
			tg_map[f'{mcc}990'] = f'{country} Text Message'
			tg_map[f'{mcc}997'] = f'{country} Parrot'
			tg_map[f'{mcc}999'] = f'{country} ARS/RRS/GPS'


class UserManager:
	"""Manages loading and caching of user data from user.csv and DMRIds.dat."""

	def __init__(self, user_csv_path='/usr/local/etc/user.csv', dmr_ids_path='/usr/local/etc/DMRIds.dat'):
		"""Initializes the UserManager."""
		self._user_csv_path = user_csv_path or '.sample/user.csv'
		self._dmr_ids_path = dmr_ids_path or '.sample/DMRids.dat'
		self._cache = {'mtime_csv': 0, 'mtime_dat': 0, 'user_map': {}}

	def get_map(self) -> dict:
		"""Returns the user map, reloading from file if it has changed."""
		try:
			mtime_csv = os.path.getmtime(self._user_csv_path)
		except OSError:
			mtime_csv = 0
		try:
			mtime_dat = os.path.getmtime(self._dmr_ids_path)
		except OSError:
			mtime_dat = 0

		if mtime_csv == self._cache.get('mtime_csv') and mtime_dat == self._cache.get('mtime_dat') and self._cache.get('user_map'):
			return self._cache['user_map']

		user_map = self._load_data()
		self._cache = {'mtime_csv': mtime_csv, 'mtime_dat': mtime_dat, 'user_map': user_map}
		return user_map

	def _load_data(self) -> dict:
		"""Loads user data, preferring user.csv and falling back to DMRIds.dat."""
		user_map = self._load_from_user_csv()
		if not user_map:
			logging.warning('Could not load user data from %s, falling back to %s.', self._user_csv_path, self._dmr_ids_path)
			user_map = self._load_from_dmr_ids()
		return user_map

	def _load_from_user_csv(self) -> dict:
		"""Loads user data from the user.csv file."""
		if not os.path.isfile(self._user_csv_path):
			return {}
		encodings = ['utf-8', 'latin-1']
		for encoding in encodings:
			try:
				user_map = {}
				with open(self._user_csv_path, 'r', encoding=encoding, errors='replace') as file:
					for line in file:
						parts = line.strip().split(',')
						if len(parts) >= 3:
							ccs7 = parts[0].strip()
							call = parts[1].strip()
							fname = parts[2].strip()
							country = parts[-1].strip()
							if call:
								user_map[call] = (ccs7, fname, country)
								user_map[ccs7] = (call, fname, country)
				logging.debug('Successfully loaded user data from %s with %s encoding.', self._user_csv_path, encoding)
				return user_map
			except UnicodeDecodeError:
				logging.warning('UnicodeDecodeError with %s for %s. Trying next.', self._user_csv_path)
			except Exception as e:
				logging.error('Error reading user file %s: %s', self._user_csv_path, e)
				break
		return {}

	def _load_from_dmr_ids(self) -> dict:
		"""Loads user data from the DMRIds.dat file."""
		if not os.path.isfile(self._dmr_ids_path):
			return {}
		encodings = ['utf-8', 'latin-1']
		for encoding in encodings:
			try:
				user_map = {}
				with open(self._dmr_ids_path, 'r', encoding=encoding, errors='replace') as file:
					for line in file:
						line = line.strip()
						if not line or line.startswith('#'):
							continue
						parts = line.split('\t')
						if len(parts) >= 3:
							ccs7 = parts[0].strip()
							call = parts[1].strip()
							fname = parts[2].strip()
							country = ''
							if ccs7.isdigit() and len(ccs7) >= 3:
								mcc = int(ccs7[:3])
								if mcc in MCC_CODES:
									country, _ = MCC_CODES[mcc]
							if call:
								user_map[call] = (ccs7, fname, country)
								user_map[ccs7] = (call, fname, country)
				logging.debug('Successfully loaded user data from %s with %s encoding.', self._dmr_ids_path, encoding)
				return user_map
			except UnicodeDecodeError:
				logging.warning('UnicodeDecodeError with %s for %s. Trying next.', encoding, self._dmr_ids_path)
			except Exception as e:
				logging.error('Error reading user file %s: %s', self._dmr_ids_path, e)
				break
		return {}
