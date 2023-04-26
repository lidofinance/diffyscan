# Diffyscan

![python ^3.10](https://img.shields.io/badge/python-^3.10-blue)
![poetry ^1.4](https://img.shields.io/badge/poetry-^1.4-blue)
![license MIT](https://img.shields.io/badge/license-MIT-brightgreen)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Diff your Ethereum smart contracts code from GitHub against Etherscan verified source code.

## Prerequisites
This project was developed using these dependencies with their exact versions listed below:
- Python 3.10
- Poetry 1.4

Other versions may work as well but were not tested at all.

## Setup

1. Install Poetry

Use the following command to install poetry:

```shell
pip install --user poetry~=1.4
```

alternatively, you could proceed with `pipx`:

```shell
pipx install poetry~=1.4
```

2. Activate poetry virtual environment,
```shell
poetry shell
```

3. Install Python dependencies
```shell
poetry install
```

## Usage

Set your Etherscan token to fetch verified source code,
```bash
export ETHERSCAN_TOKEN=<your-etherscan-token>
```

Set your Github token to query API without strict rate limiting,
```bash
export GITHUB_API_TOKEN=<your-github-token>
```

Create a config file
```json
{
    "contract": "0x...",
    "network": "mainnet",
    "github_repo": "https://github.com/user/repo/tree/ref",
    "dependencies": {
        "dep_name": "https://github.com/user/repo/tree/ref"
    }
}
```

Start the script
```bash
python3 main.py
```
