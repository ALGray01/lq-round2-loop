'use strict';

const { createApp, getAdminToken } = require('./src/server');

const PORT = process.env.PORT || 3000;
const app = createApp();

app.listen(PORT, () => {
  console.log(`explainer-link-delivery listening on http://localhost:${PORT}`);
  console.log(`Admin token (send as x-admin-token header): ${getAdminToken()}`);
});
