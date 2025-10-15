import type { HardhatUserConfig } from "hardhat/config";

const config: HardhatUserConfig = {
  solidity: "0.8.9",
  networks: {
    hardhat: {
      type: "edr-simulated",
      chainId: 11155420,
      blockGasLimit: 92000000,
      hardfork: "cancun",
    },
  },
};

export default config;
