/** @type {import('sequelize').Options} */
const coerceLogging = (value) => {
  if (typeof value === 'function') {
    return value;
  }
  if (!value) {
    return false;
  }
  const normalised = String(value).toLowerCase();
  if (normalised === 'true' || normalised === 'console') {
    return console.log; // eslint-disable-line no-console
  }
  if (normalised === 'false' || normalised === '0') {
    return false;
  }
  return value;
};

module.exports = {
  development: {
    username: process.env.DEV_DB_USERNAME,
    password: process.env.DEV_DB_PASSWORD,
    database: process.env.DEV_DB_NAME,
    host: process.env.DEV_DB_HOSTNAME,
    dialect: process.env.DEV_DB_DIALECT,
    logging: coerceLogging(process.env.DEV_DB_LOGGING),
  },
  test: {
    username: process.env.TEST_DB_USERNAME,
    password: process.env.TEST_DB_PASSWORD,
    database: process.env.TEST_DB_NAME,
    host: process.env.TEST_DB_HOSTNAME,
    dialect: process.env.TEST_DB_DIALECT,
    logging: coerceLogging(process.env.TEST_DB_LOGGING),
  },
  production: {
    username: process.env.PROD_DB_USERNAME,
    password: process.env.PROD_DB_PASSWORD,
    database: process.env.PROD_DB_NAME,
    host: process.env.PROD_DB_HOSTNAME,
    dialect: process.env.PROD_DB_DIALECT,
    logging: coerceLogging(process.env.PROD_DB_LOGGING),
  },
};
