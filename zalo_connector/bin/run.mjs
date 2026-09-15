import {LoginQRCallbackEventType, Zalo} from 'zca-js';

import {startConnector} from '../src/connector.mjs';

try {
  const connector = await startConnector({Zalo, LoginQRCallbackEventType});
  const stop = () => {
    connector.close();
    process.exit(0);
  };
  process.once('SIGINT', stop);
  process.once('SIGTERM', stop);
} catch (error) {
  // Never print session cookies, signed URLs, or secrets from third-party errors.
  process.stderr.write(`Zalo connector stopped (${error?.name || 'Error'}).\n`);
  process.exit(1);
}
