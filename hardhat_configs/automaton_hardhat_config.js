module.exports = {
  solidity: "0.8.9",
  networks: {
    hardhat: {
      chainId: process.env.CHAIN_ID,
      blockGasLimit: 92000000,
      hardfork: "cancun",
    }
  },
};
