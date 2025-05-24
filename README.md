# Diffyscan

![python >=3.10,<4](https://img.shields.io/badge/python-≥3.10,<4-blue)
![poetry ^1.8](https://img.shields.io/badge/poetry-^1.8-blue)
![NodeJs >=20](https://img.shields.io/badge/NodeJS-≥20-yellow)
![license MIT](https://img.shields.io/badge/license-MIT-brightgreen)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Diff deployed EVM-compatible smart contract sourcecode and bytecode against the specified GitHub repo commit.

Key features:

- retrieve and diff sources from the GitHub repo against the queried ones from a blockscan service (e.g. Etherscan)
- compare the bytecode compiled and deployed on the forked network locally against remote (see section 'bytecode_comparison' in `./config_samples/lido_dao_sepolia_config.json` as an example)
- preprocess solidity sourcecode by means of prettier solidity plugin before comparing the sources (option `--prettify`) if needed.
- preprocess imports to flat paths for Brownie compatibility (option `--support-brownie`)
- enable binary comparison (option `--enable-binary-comparison`)
- provide own Hardhat config as optional argument

## Install

```bash
pipx install git+https://github.com/lidofinance/diffyscan
```

If deployed bytecode binary comparison or prettier source preprocessing are needed:

```shell
npm install
```

## Usage

Set your Etherscan token to fetch verified source code,

```bash
export ETHERSCAN_EXPLORER_TOKEN=<your-etherscan-token>
```

Set your Github token to query API without strict rate limiting,

```bash
export GITHUB_API_TOKEN=<your-github-token>
```

Set remote RPC URL to validate contract bytecode at remote rpc node,

```bash
export REMOTE_RPC_URL =<remote-rpc-url>
```

Set local RPC URL to check immutables against the local deployment and provided constructor arguments,

```bash
export LOCAL_RPC_URL =<local-rpc-url> (example `http://127.0.0.1:7545`)
```

Start script with one of the examples provided (or entire folder of configs)

```bash
diffyscan config_samples/lido_dao_sepolia_config.json
```

Alternatively, create a new config file named `config.json` near the diffyscan.py,

```json
{
  "contracts": {
    "0x28FAB2059C713A7F9D8c86Db49f9bb0e96Af1ef8": "OssifiableProxy",
    "0xDba5Ad530425bb1b14EECD76F1b4a517780de537": "LidoLocator"
  },
  "explorer_hostname": "api.etherscan.io",
  "explorer_chain_id": 17000,
  "explorer_token_env_var": "ETHERSCAN_EXPLORER_TOKEN",
  "github_repo": {
    "url": "https://github.com/lidofinance/lido-dao",
    "commit": "cadffa46a2b8ed6cfa1127fca2468bae1a82d6bf",
    "relative_root": ""
  },
  "dependencies": {
    "@openzeppelin/contracts-v4.4": {
      "url": "https://github.com/OpenZeppelin/openzeppelin-contracts",
      "commit": "6bd6b76d1156e20e45d1016f355d154141c7e5b9",
      "relative_root": "contracts"
    }
  },
  "fail_on_bytecode_comparison_error": true,
  "bytecode_comparison": {
    "hardhat_config_name": "holesky_hardhat.config.js",
    "constructor_calldata": {
      "0x28FAB2059C713A7F9D8c86Db49f9bb0e96Af1ef8": "000000000000000000000000ab89ed3d8f31bcf8bb7de53f02084d1e6f043d34000000000000000000000000e92329ec7ddb11d25e25b3c21eebf11f15eb325d00000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000000000000000000000000000"
    },
    "constructor_args": {
      "0xDba5Ad530425bb1b14EECD76F1b4a517780de537": [
        [
          "0x4E97A3972ce8511D87F334dA17a2C332542a5246",
          "0x045dd46212A178428c088573A7d102B9d89a022A",
          "0xE73a3602b99f1f913e72F8bdcBC235e206794Ac8",
          "0x072f72BE3AcFE2c52715829F2CD9061A6C8fF019",
          "0x3F1c547b21f65e10480dE3ad8E19fAAC46C95034",
          "0xF0d576c7d934bBeCc68FE15F1c5DAF98ea2B78bb",
          "0x072f72BE3AcFE2c52715829F2CD9061A6C8fF019",
          "0x4E46BD7147ccf666E1d73A3A456fC7a68de82eCA",
          "0xd6EbF043D30A7fe46D1Db32BA90a0A51207FE229",
          "0xE92329EC7ddB11D25e25b3c21eeBf11f15eB325d",
          "0xffDDF7025410412deaa05E3E1cE68FE53208afcb",
          "0xc7cc160b58F8Bb0baC94b80847E2CF2800565C50",
          "0xF0179dEC45a37423EAD4FaD5fCb136197872EAd9",
          "0xC01fC1F2787687Bc656EAc0356ba9Db6e6b7afb7"
        ]
      ]
    }
  }
}
```

then create a new Hardhat config file named `hardhat_config.js` near the diffyscan.py

```js
module.exports = {
  solidity: "0.8.9",
  networks: {
    hardhat: {
      chainId: 17000,
      blockGasLimit: 92000000,
      hardfork: "cancun",
    },
  },
};
```

> Note: Hardhat config file is needed to avoid standard config generation routine to be launched.
>
> See also: https://hardhat.org/hardhat-runner/docs/config#configuration

Start the script

```bash
diffyscan /path/to/config.json /path/to/hardhat_config.js --enable-binary-comparison
```

> Note: Brownie verification tooling might rewrite the imports in the source submission. It transforms relative paths to imported contracts into flat paths ('./folder/contract.sol' -> 'contract.sol'), which makes Diffyscan unable to find a contract for verification.

For contracts whose sources were verified by brownie tooling:

```bash
diffyscan /path/to/config.json /path/to/hardhat_config.js --enable-binary-comparison --support-brownie
```

ℹ️ See more config examples inside the [config_samples](./config_samples/) dir.

## Development setup

### Prerequisites

This project was developed using these dependencies with their exact versions listed below:

- Python 3.12
- Poetry 1.8
- if deployed bytecode binary comparison or prettier source preprocessing are needed:
  - npm

Other versions may work as well but were not tested at all.

### Setup

1. Install Poetry

Use the following command to install poetry:

```bash
pip install --user poetry~=1.8
```

alternatively, you could proceed with `pipx`:

```bash
pipx install poetry~=1.8
```

2. Activate poetry virtual environment,

```bash
poetry shell
```

3. Install [poetry-dynamic-versioning](https://github.com/mtkennerly/poetry-dynamic-versioning?tab=readme-ov-file#installation)

- In most cases: `poetry self add "poetry-dynamic-versioning[plugin]"`
- If you installed Poetry with Pipx: `pipx inject poetry "poetry-dynamic-versioning[plugin]"`

4. Install Python dependencies

```bash
poetry install
```

5. If deployed bytecode binary comparison or prettier source preprocessing are needed:

```shell
npm install
```
