'use strict';

// Plantilla PM2 inerte: cargar este módulo solo exporta configuración.
// No instala PM2, inicia procesos ni modifica servicios.
const root = '/home/petrov/botsky';

module.exports = {
  apps: [
    {
      name: 'botsky-production-runtime',
      cwd: root,
      script: `${root}/.venv/bin/python`,
      args: [
        '-m',
        'botsky.connected',
        '--config',
        `${root}/private/production/config.toml`,
        '--providers',
        `${root}/private/integrations.production.json`,
        'serve',
      ],
      interpreter: 'none',
      exec_mode: 'fork',
      instances: 1,
      autorestart: true,
      watch: false,
      time: true,
      env: {
        PYTHONUNBUFFERED: '1',
      },
      out_file: `${root}/private/production/pm2-runtime-out.log`,
      error_file: `${root}/private/production/pm2-runtime-error.log`,
      merge_logs: true,
      kill_timeout: 60000,
    },
    {
      name: 'botsky-production-webhook-bridge',
      cwd: root,
      script: '/usr/bin/socat',
      args: [
        '-T',
        '10',
        'TCP-LISTEN:3000,bind=172.18.0.1,reuseaddr,fork,max-children=32',
        'TCP:127.0.0.1:18787',
      ],
      interpreter: 'none',
      exec_mode: 'fork',
      instances: 1,
      autorestart: true,
      watch: false,
      time: true,
      out_file: `${root}/private/production/pm2-bridge-out.log`,
      error_file: `${root}/private/production/pm2-bridge-error.log`,
      merge_logs: true,
      kill_timeout: 10000,
    },
  ],
};
