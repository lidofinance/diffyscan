import type { HardhatUserConfig } from "hardhat/config";

const config: HardhatUserConfig = {
  solidity: "0.8.30",
  networks: {
    hardhat: {
      type: "edr-simulated",
      chainId: 9745,
      blockGasLimit: 92000000,
      hardfork: "prague",
    },
  },
};

export default config;
