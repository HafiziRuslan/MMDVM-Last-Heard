# MMDVM Last Heard Bot

![Ko-Fi sponsors](https://img.shields.io/badge/kofi-tip-FF6433?style=for-the-badge&logo=kofi&logoColor=FF6433&logoSize=auto&link=https%3A%2F%2Fko-fi.com%2Fhafiziruslan)
![Buy me a Coffee sponsors](https://img.shields.io/badge/buymeacoffee-tip-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=FFDD00&logoSize=auto&link=https%3A%2F%2Fwww.buymeacoffee.com%2Fhafiziruslan)
![PayPal sponsors](https://img.shields.io/badge/paypal-tip-002991?style=for-the-badge&logo=paypal&logoColor=002991&logoSize=auto&link=https%3A%2F%2Fpaypal.me%2FHafiziRuslan)
![Stripe sponsors](https://img.shields.io/badge/stripe-tip-635BFF?style=for-the-badge&logo=stripe&logoColor=635BFF&logoSize=auto&link=https%3A%2F%2Fdonate.stripe.com%2F5kA9CJg7S1J8bx64gg)

![GitHub Sponsors](https://img.shields.io/github/sponsors/hafiziruslan?style=for-the-badge&logo=githubsponsors&logoColor=EA4AAA&logoSize=auto&color=EA4AAA&link=https%3A%2F%2Fgithub.com%2Fsponsors%2FHafiziRuslan)
![Open Collective sponsors](https://img.shields.io/opencollective/sponsors/hafiziruslan?style=for-the-badge&logo=opencollective&logoColor=7FADF2&logoSize=auto&link=https%3A%2F%2Fopencollective.com%2Fhafiziruslan)
![thanks.dev sponsors](https://img.shields.io/badge/sponsors-thanks.dev-black?style=for-the-badge&logoSize=auto&link=https%3A%2F%2Fthanks.dev%2F%2Fgh%2Fhafiziruslan)

This project is a Python-based Telegram bot that monitors MMDVM logs and sends updates to a specified Telegram chat. It uses the `python-telegram-bot` library to interact with Telegram and parses MMDVM log files to extract relevant information.

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/hafiziruslan)

Mirrors (daily update):

- GitLab: <https://gitlab.com/hafiziruslan/MMDVM-LastHeard>
- Codeberg: <https://codeberg.org/hafiziruslan/MMDVM-LastHeard>
- Gitea: <https://gitea.com/HafiziRuslan/MMDVM-LastHeard>

## Features

- Monitors MMDVM log files for new entries.
- Parses log entries and formats them into readable messages.
- Sends updates to a Telegram chat using a bot.
- Configurable via environment variables.

## Prerequisites

- Python 3.13 or higher
- A Telegram bot token (create one using [BotFather](https://core.telegram.org/bots#botfather)).
- A Telegram chat ID where the bot will send messages.
- Access to the DStar log files on your Pi-Star system.

## 🛠️ Installation

```bash
git clone https://github.com/HafiziRuslan/MMDVM-LastHeard.git MMDVM-LastHeard
cd MMDVM-LastHeard
```

## ⚙️ Configuration

Copy the file `default.env` into `.env`, and edit the configuration using your favorite editor.

```bash
cp default.env .env
nano .env
```

## AutoStart

Copy & Paste this line into last line (before blank line) of `/etc/crontab` or any other cron program that you're using.

```bash
@reboot pi-star cd /home/pi-star/MMDVM-LastHeard && ./main.sh > /var/log/MMDVM-LastHeard.log 2>&1
```

change the `pi-star` username into your username

## Update

Manual update are **NOT REQUIRED** as it has integrated into `main.sh`.

Use this command for manual update:-

```bash
git pull --autostash
```

## 🚀 Usage

Run the main script with root privileges. This script automatically:

- Checks for and installs system dependencies (`gcc`, `git`, `python3-dev`, `curl`).
- Installs `uv` and sets up the Python virtual environment.
- Updates the repository to the latest version.
- Runs the application in a monitoring loop.

```bash
sudo ./main.sh
```

Note: to install uv using `apt`, you may use `debian.griffo.io` repository.

```bash
curl -sS https://debian.griffo.io/EA0F721D231FDD3A0A17B9AC7808B4DD62C41256.asc | sudo gpg --dearmor --yes -o /etc/apt/trusted.gpg.d/debian.griffo.io.gpg

echo "deb https://debian.griffo.io/apt $(lsb_release -sc 2>/dev/null) main" | sudo tee /etc/apt/sources.list.d/debian.griffo.io.list

sudo apt update && sudo apt install uv
```

## Logging

The bot uses Python's `logging` module to log events and errors. Logs are displayed in the console for easy debugging.

### Source

[iu2frl/pistar-lastheard-telegram](https://github.com/iu2frl/pistar-lastheard-telegram)
