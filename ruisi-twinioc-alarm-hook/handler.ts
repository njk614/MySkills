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
    cfg?: {
      hooks?: {
        internal?: {
          entries?: {
            'ruisi-twinioc-alarm-hook'?: {
              env?: Record<string, string>;
            };
          };
        };
      };
    };
  };
};

type EnvSource = 'hook' | 'process' | 'default';

type EnvSpec = {
  key: string;
  aliases: string[];
};

type EnvResolution = {
  key: string;
  value?: string;
  source: EnvSource;
};

const FORWARDED_ENV_SPECS: EnvSpec[] = [
  { key: 'OPENCLAW_HOOK_TOKEN', aliases: ['openclaw_hook_token', 'openclawHookToken'] },
  { key: 'ALERT_RECIPIENTS_JSON', aliases: ['alert_recipients_json', 'alertRecipientsJson'] },
  { key: 'OPENCLAW_HOOK_BASE_URL', aliases: ['openclaw_hook_base_url', 'openclawHookBaseUrl'] },
  { key: 'MQTT_URL', aliases: ['mqtt_url', 'mqttUrl'] },
  { key: 'MQTT_USERNAME', aliases: ['mqtt_username', 'mqttUsername'] },
  { key: 'MQTT_PASSWORD', aliases: ['mqtt_password', 'mqttPassword'] },
  { key: 'MQTT_TOPIC', aliases: ['mqtt_topic', 'mqttTopic'] },
  { key: 'MQTT_CLIENT_ID', aliases: ['mqtt_client_id', 'mqttClientId'] },
  { key: 'MQTT_QOS', aliases: ['mqtt_qos', 'mqttQos'] },
  { key: 'HTTP_TIMEOUT_SECONDS', aliases: ['http_timeout_seconds', 'httpTimeoutSeconds'] },
  { key: 'MQTT_LOG_LEVEL', aliases: ['mqtt_log_level', 'mqttLogLevel'] },
  { key: 'OPENCLAW_CLI_BIN', aliases: ['openclaw_cli_bin', 'openclawCliBin'] },
  { key: 'ALERT_TITLE', aliases: ['alert_title', 'alertTitle'] },
];

function normalizeEnvValue(value: unknown): string | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  const text = String(value).trim();
  return text ? text : undefined;
}

function findEnvValue(
  env: Record<string, unknown>,
  key: string,
  aliases: string[]
): string | undefined {
  const candidates = [key, ...aliases];

  // Prefer exact key order first.
  for (const candidate of candidates) {
    const value = normalizeEnvValue(env[candidate]);
    if (value !== undefined) {
      return value;
    }
  }

  // Fallback to case-insensitive lookup for Linux/Windows compatibility.
  const lowerCandidates = new Set(candidates.map((entry) => entry.toLowerCase()));
  for (const [rawKey, rawValue] of Object.entries(env)) {
    if (!lowerCandidates.has(rawKey.toLowerCase())) {
      continue;
    }
    const value = normalizeEnvValue(rawValue);
    if (value !== undefined) {
      return value;
    }
  }

  return undefined;
}

export function resolveEnvValue(
  key: string,
  aliases: string[],
  hookEnv: Record<string, unknown>,
  parentEnv: Record<string, unknown>
): EnvResolution {
  const fromHook = findEnvValue(hookEnv, key, aliases);
  if (fromHook !== undefined) {
    return { key, value: fromHook, source: 'hook' };
  }

  const fromParent = findEnvValue(parentEnv, key, aliases);
  if (fromParent !== undefined) {
    return { key, value: fromParent, source: 'process' };
  }

  return { key, source: 'default' };
}

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

  const hookConfig = event.context?.cfg?.hooks?.internal?.entries?.['ruisi-twinioc-alarm-hook'];
  const hookEnv = (hookConfig?.env || {}) as Record<string, unknown>;
  const resolvedEnvs = FORWARDED_ENV_SPECS.map((spec) => ({
    spec,
    resolution: resolveEnvValue(spec.key, spec.aliases, hookEnv, process.env),
  }));

  const stateDir = path.join(workspaceDir, '.openclaw-ruisi-twinioc-alarm-hook');
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

  const childEnv: NodeJS.ProcessEnv = {
    ...process.env,
    WORKSPACE_DIR: workspaceDir,
    ALARM_MQTT_STATE_DIR: stateDir,
    ALARM_MQTT_PID_FILE: pidFile,
  };

  for (const { spec, resolution } of resolvedEnvs) {
    if (resolution.value !== undefined) {
      childEnv[spec.key] = resolution.value;
    }
  }

  const child = spawn(process.execPath, [subscriberPath], {
    cwd: hookDir,
    detached: true,
    env: childEnv,
    stdio: 'ignore',
    windowsHide: true,
  });

  child.unref();
  writeFileSync(pidFile, String(child.pid));
  console.log(`[ruisi-twinioc-alarm-hook] Started subscriber with PID ${child.pid}.`);
  for (const { spec, resolution } of resolvedEnvs) {
    const valueState = resolution.value ? 'set' : 'missing';
    console.log(`[ruisi-twinioc-alarm-hook] ENV ${spec.key}: source=${resolution.source} value=${valueState}`);
  }
  event.messages?.push('MQTT alarm pusher started in background.');
}
