module.exports = {
  solidity: "0.8.9",
  networks: {
    hardhat: {
      allowUnlimitedContractSize: true,
      chainId: 17000,
      blockGasLimit: 92000000,
      hardfork: "cancun",
    }
  },
};
