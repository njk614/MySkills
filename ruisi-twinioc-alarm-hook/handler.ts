import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

type HookEvent = {
  type?: string;
  action?: string;
  messages?: string[];
  context?: {
    workspaceDir?: string;
  };
};

function isProcessRunning(pid: number): boolean {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }

  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

const hookDir = path.dirname(fileURLToPath(import.meta.url));

export default async function handler(event: HookEvent): Promise<void> {
  if (event.type !== 'gateway' || event.action !== 'startup') {
    return;
  }

  const workspaceDir = event.context?.workspaceDir;
  if (!workspaceDir) {
    console.error('[ruisi-twinioc-alarm-hook] Missing workspaceDir in hook context.');
    return;
  }

  const stateDir = path.join(workspaceDir, '.openclaw-alarm-mqtt');
  const pidFile = path.join(stateDir, 'subscriber.pid');
  const subscriberPath = path.join(hookDir, 'subscriber.mjs');

  mkdirSync(stateDir, { recursive: true });

  try {
    const existingPid = Number.parseInt(readFileSync(pidFile, 'utf8').trim(), 10);
    if (isProcessRunning(existingPid)) {
      console.log(`[ruisi-twinioc-alarm-hook] Subscriber already running with PID ${existingPid}.`);
      return;
    }
  } catch {
    // No existing pid file or unreadable content; spawn a new subscriber.
  }

  const child = spawn(process.execPath, [subscriberPath], {
    cwd: hookDir,
    detached: true,
    env: {
      ...process.env,
      WORKSPACE_DIR: workspaceDir,
      ALARM_MQTT_STATE_DIR: stateDir,
      ALARM_MQTT_PID_FILE: pidFile,
    },
    stdio: 'ignore',
    windowsHide: true,
  });

  child.unref();
  writeFileSync(pidFile, String(child.pid));
  console.log(`[ruisi-twinioc-alarm-hook] Started subscriber with PID ${child.pid}.`);
  event.messages?.push('MQTT alarm pusher started in background.');
}
