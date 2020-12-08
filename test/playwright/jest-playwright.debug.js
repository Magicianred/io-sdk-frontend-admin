// https://github.com/playwright-community/jest-playwright/#configuration
module.exports = {
  browsers: ["chromium"],
  launchOptions: {
    headless: false,
    slowMo: 100
  }
}
