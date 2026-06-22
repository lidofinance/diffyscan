# L2 solc standard-JSON inputs

These files are the `local_compilation.inputs` for the mev-commit chain (57173)
configs (`primev_l2_v1.2.0.yaml`, `primev_l2_v1.2.1.yaml`). diffyscan uses them
only for the **source file manifest** (the list of paths that make up each
contract) and the **compiler settings** (optimizer, viaIR, evmVersion,
remappings, libraries). File contents are fetched from GitHub at the pinned
commit during compilation, so the `sources[*].content` fields are intentionally
left empty here — keeping them would just duplicate what already lives in git.

Everything in these files is derived from the pinned commit and can be
regenerated. From a checkout of `primev/mev-commit` at the config's commit:

```bash
forge verify-contract --show-standard-json-input \
  0x0000000000000000000000000000000000000000 \
  contracts/core/BidderRegistry.sol:BidderRegistry \
  | jq '.sources |= map_values({content: ""})' > BidderRegistry.json
```

Tags: v1.2.0 (`e01198b3…`) for BidderRegistry, PreconfManager, Oracle,
BlockTracker, SettlementGateway; v1.2.1 (`28a54c02…`) for ProviderRegistryV2.
