# Diffyscan

Diff your Github code against Etherscan verified source code.

## Usage

Set your Etherscan token to fetch verified source code,
```bash
export ETHERSCAN_API_TOKEN=<your-etherscan-token>
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
