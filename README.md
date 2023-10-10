# Diffyscan

![python ^3.10](https://img.shields.io/badge/python-^3.10-blue)
![poetry ^1.4](https://img.shields.io/badge/poetry-^1.6-blue)
![license MIT](https://img.shields.io/badge/license-MIT-brightgreen)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Diff your Ethereum smart contracts code from GitHub against Blockchain explorer verified source code.

## Prerequisites

This project was developed using these dependencies with their exact versions listed below:

- Python 3.10
- Poetry 1.6

Other versions may work as well but were not tested at all.

## Setup

1. Install Poetry

Use the following command to install poetry:

```shell
pip install --user poetry~=1.6
```

alternatively, you could proceed with `pipx`:

```shell
pipx install poetry~=1.6
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
    "contracts": {
        "0x28FAB2059C713A7F9D8c86Db49f9bb0e96Af1ef8": "OssifiableProxy",
        "0xDba5Ad530425bb1b14EECD76F1b4a517780de537": "LidoLocator",
    },
    "explorer_hostname": "api-holesky.etherscan.io",
    "github_repo": "https://github.com/lidofinance/lido-dao",
    "dependencies": {
        "@aragon/apps-agent": {
            "url": "https://github.com/lidofinance/aragon-apps/",
            "commit": "b09834d29c0db211ddd50f50905cbeff257fc8e0",
            "relative_root": "apps/agent"
        }
        "@openzeppelin/contracts-v4.4": {
            "url": "https://github.com/OpenZeppelin/openzeppelin-contracts",
            "commit": "6bd6b76d1156e20e45d1016f355d154141c7e5b9",
            "relative_root": "contracts"
        }
    }
}
```

ℹ️ See more examples inside the [config_samples](./config_samples/) dir.

Start the script

```bash
python3 main.py
```
