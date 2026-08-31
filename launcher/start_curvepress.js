// CurvePress Studio Windows one-click launcher.
// This file is bundled into Start.exe for the Windows release package.
// The launcher only starts the existing local batch file; the app itself
// remains in the same folder and keeps its portable Python runtime.
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const root = path.dirname(process.execPath);
const batch = path.join(root, 'run_curvepress.bat');
const log = path.join(root, 'curvepress-start.log');
try {
  fs.appendFileSync(log, `${new Date().toISOString()} launcher root=${root} batch=${batch} exists=${fs.existsSync(batch)}\r\n`);
} catch (_) {
  // Continue to the normal launcher path even if the folder is read-only.
}

if (!fs.existsSync(batch)) {
  process.exitCode = 1;
} else {
  const child = spawn(process.env.ComSpec || 'cmd.exe', ['/d', '/c', 'call', batch], {
    cwd: root,
    windowsHide: true,
    stdio: 'ignore',
  });

  child.on('error', (error) => {
    try {
      fs.appendFileSync(log, `${new Date().toISOString()} launcher error: ${error.message}\r\n`);
    } catch (_) {
      // The batch file remains the source of truth for startup diagnostics.
    }
    process.exitCode = 1;
  });
}

