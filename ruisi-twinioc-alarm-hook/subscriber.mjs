import { createHash } from 'node:crypto';
import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import mqtt from 'mqtt';

const DEFAULT_MQTT_URL = 'mqtts://y9afbaf6.ala.cn-hangzhou.emqxsl.cn:8883';
const DEFAULT_MQTT_USERNAME = 'twinioc';
const DEFAULT_MQTT_PASSWORD = 'abc123';
const DEFAULT_MQTT_TOPIC = 'twineasy/location/dyo6vaow6203kx09/alarm/changed/v1';
const TARGET_BELONG_TO_LOCATION_ID = 'dyo6vaow6203kx09';
const DEFAULT_OPENCLAW_HOOK_BASE_URL = 'http://127.0.0.1:18789';
const DEFAULT_ALERT_TITLE = '告警通知';
const PUSH_RETRY_DELAYS_MS = [0, 500, 1500];
const NO_ALARM_TEXT = new Set(['', 'null', '[]', '{}', '""']);

const workspaceDir = process.env.WORKSPACE_DIR || process.cwd();
const stateDir = process.env.ALARM_MQTT_STATE_DIR || path.join(workspaceDir, '.openclaw-ruisi-twinioc-alarm-hook');
const pidFile = process.env.ALARM_MQTT_PID_FILE || path.join(stateDir, 'subscriber.pid');
const logFile = path.join(stateDir, 'subscriber.log');
const consumerStateFile = path.join(stateDir, 'consumer.state.json');

const mqttUrl = process.env.MQTT_URL || DEFAULT_MQTT_URL;
const mqttUsername = process.env.MQTT_USERNAME || DEFAULT_MQTT_USERNAME;
const mqttPassword = process.env.MQTT_PASSWORD || DEFAULT_MQTT_PASSWORD;
const mqttTopic = process.env.MQTT_TOPIC || DEFAULT_MQTT_TOPIC;
const mqttClientId = process.env.MQTT_CLIENT_ID;
const configuredQos = Number.parseInt(process.env.MQTT_QOS || '1', 10);
const mqttQos = Number.isInteger(configuredQos) && configuredQos >= 0 && configuredQos <= 2 ? configuredQos : 1;
const httpTimeoutSeconds = Number.parseFloat(process.env.HTTP_TIMEOUT_SECONDS || '10');
const timeoutMs = Number.isFinite(httpTimeoutSeconds) && httpTimeoutSeconds > 0 ? httpTimeoutSeconds * 1000 : 10000;
const logLevel = (process.env.MQTT_LOG_LEVEL || 'info').toLowerCase();
const alertTitle = process.env.ALERT_TITLE || DEFAULT_ALERT_TITLE;
const openclawHookBaseUrl = (process.env.OPENCLAW_HOOK_BASE_URL || DEFAULT_OPENCLAW_HOOK_BASE_URL).trim();
const openclawHookToken = (process.env.OPENCLAW_HOOK_TOKEN || '').trim();

mkdirSync(stateDir, { recursive: true });
writeFileSync(pidFile, String(process.pid));

function log(message) {
  const line = `[${new Date().toISOString()}] ${message}`;
  console.log(line);
  appendFileSync(logFile, `${line}\n`);
}

function cleanup() {
  try {
    if (existsSync(pidFile)) {
      unlinkSync(pidFile);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    log(`Cleanup warning: ${message}`);
  }
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function buildAgentEndpoint() {
  const base = openclawHookBaseUrl.replace(/\/+$/, '');
  if (base.endsWith('/hooks')) {
    return `${base}/agent`;
  }
  return `${base}/hooks/agent`;
}

function isDebugLogEnabled() {
  return logLevel === 'debug';
}

function tryParseJson(payloadText) {
  try {
    return JSON.parse(payloadText);
  } catch {
    return null;
  }
}

function normalizeFieldValue(value) {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return null;
}

function pickField(value, keys) {
  if (value === null || value === undefined) {
    return null;
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const found = pickField(item, keys);
      if (found !== null) {
        return found;
      }
    }
    return null;
  }

  if (typeof value === 'object') {
    for (const key of keys) {
      const found = normalizeFieldValue(value[key]);
      if (found !== null) {
        return found;
      }
    }
    for (const nested of Object.values(value)) {
      const found = pickField(nested, keys);
      if (found !== null) {
        return found;
      }
    }
  }

  return null;
}

function containsAlarm(value) {
  if (value === null || value === undefined) {
    return false;
  }

  if (Array.isArray(value)) {
    return value.length > 0;
  }

  if (typeof value === 'object') {
    for (const key of ['alarmData', 'alarms', 'alarmList', 'items', 'records', 'rows', 'data', 'result']) {
      if (key in value && containsAlarm(value[key])) {
        return true;
      }
    }

    for (const key of ['total', 'count', 'size', 'alarmCount', 'recordCount']) {
      const count = value[key];
      if (typeof count === 'number' && count > 0) {
        return true;
      }
    }

    for (const nested of Object.values(value)) {
      if ((Array.isArray(nested) || typeof nested === 'object') && containsAlarm(nested)) {
        return true;
      }
    }
  }

  return false;
}

function hasAlarmData(parsedPayload, payloadText) {
  if (parsedPayload === null) {
    return !NO_ALARM_TEXT.has(payloadText.trim().toLowerCase());
  }
  return containsAlarm(parsedPayload);
}

function canonicalize(value) {
  if (Array.isArray(value)) {
    return value.map((entry) => canonicalize(entry));
  }

  if (value && typeof value === 'object') {
    return Object.keys(value)
      .sort()
      .reduce((result, key) => ({ ...result, [key]: canonicalize(value[key]) }), {});
  }

  return value;
}

function buildAlarmSignature(topic, payload) {
  const canonicalPayload = JSON.stringify(canonicalize(payload));
  return createHash('sha256').update(`${topic}\n${canonicalPayload}`).digest('hex');
}

function recipientKey(recipient) {
  return `${recipient.channel}:${recipient.to}`;
}

function parseRecipients() {
  const raw = process.env.ALERT_RECIPIENTS_JSON;
  if (!raw) {
    throw new Error('ALERT_RECIPIENTS_JSON is required and must be a JSON array.');
  }

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error('ALERT_RECIPIENTS_JSON is not valid JSON.');
  }

  if (!Array.isArray(parsed)) {
    throw new Error('ALERT_RECIPIENTS_JSON must be a JSON array.');
  }

  const recipients = [];
  const seen = new Set();

  for (const entry of parsed) {
    if (!entry || typeof entry !== 'object') {
      throw new Error('Each recipient must be an object with channel and to.');
    }

    const channel = typeof entry.channel === 'string' ? entry.channel.trim() : '';
    const to = typeof entry.to === 'string' ? entry.to.trim() : '';
    if (!channel || !to) {
      throw new Error('Each recipient requires non-empty channel and to.');
    }

    const key = `${channel}:${to}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    recipients.push({ channel, to });
  }

  if (recipients.length === 0) {
    throw new Error('ALERT_RECIPIENTS_JSON must contain at least one recipient.');
  }

  return recipients;
}

function loadConsumerState() {
  if (!existsSync(consumerStateFile)) {
    return { recipientSignatures: {} };
  }

  try {
    const parsed = JSON.parse(readFileSync(consumerStateFile, 'utf8'));
    const recipientSignatures = {};
    if (parsed && typeof parsed === 'object' && parsed.recipientSignatures && typeof parsed.recipientSignatures === 'object') {
      for (const [key, value] of Object.entries(parsed.recipientSignatures)) {
        if (typeof value === 'string' && value) {
          recipientSignatures[key] = value;
        }
      }
    }
    return { recipientSignatures };
  } catch {
    return { recipientSignatures: {} };
  }
}

function saveConsumerState(state) {
  const statePayload = {
    recipientSignatures: state.recipientSignatures,
    updatedAt: new Date().toISOString(),
  };
  const tmpFile = `${consumerStateFile}.tmp`;
  writeFileSync(tmpFile, JSON.stringify(statePayload, null, 2), 'utf8');
  renameSync(tmpFile, consumerStateFile);
}

function localizeSeverity(rawSeverity) {
  const text = rawSeverity === null || rawSeverity === undefined ? '' : String(rawSeverity).trim();
  if (text === '1') {
    return '特别严重';
  }
  if (text === '2') {
    return '严重';
  }
  if (text === '3') {
    return '较重';
  }
  return '一般';
}

function formatDisplayTime(rawValue, fallbackDate) {
  const fallback = new Date(fallbackDate);
  const candidateText = rawValue ? String(rawValue).trim() : '';
  if (!candidateText) {
    return formatDisplayTime(fallback.toISOString(), fallback.toISOString());
  }

  const parsed = new Date(candidateText);
  if (Number.isNaN(parsed.getTime())) {
    return candidateText;
  }

  const yyyy = parsed.getFullYear();
  const mm = String(parsed.getMonth() + 1).padStart(2, '0');
  const dd = String(parsed.getDate()).padStart(2, '0');
  const hh = String(parsed.getHours()).padStart(2, '0');
  const mi = String(parsed.getMinutes()).padStart(2, '0');
  const ss = String(parsed.getSeconds()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
}

function parseJsonObject(value) {
  if (!value) {
    return null;
  }
  if (typeof value === 'object') {
    return value;
  }
  if (typeof value !== 'string') {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  try {
    const parsed = JSON.parse(trimmed);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function extractAlarmRecords(payloadObject) {
  if (!payloadObject) {
    return [];
  }

  if (Array.isArray(payloadObject)) {
    return payloadObject.filter((entry) => entry && typeof entry === 'object');
  }

  const candidates = [
    payloadObject.Data,
    payloadObject.data,
    payloadObject.AlarmData,
    payloadObject.alarmData,
    payloadObject.alarms,
    payloadObject.records,
    payloadObject.items,
    payloadObject.rows,
    payloadObject.result,
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      const records = candidate.filter((entry) => entry && typeof entry === 'object');
      if (records.length > 0) {
        return records;
      }
    }
  }

  if (payloadObject && typeof payloadObject === 'object') {
    return [payloadObject];
  }

  return [];
}

function filterRecordsByLocation(records, targetLocationId) {
  if (!Array.isArray(records) || records.length === 0) {
    return [];
  }
  return records.filter((item) => {
    if (!item || typeof item !== 'object') {
      return false;
    }
    const locationId = pickField(item, ['BelongToLocationID', 'belongToLocationID', 'belongToLocationId']);
    return locationId === targetLocationId;
  });
}

function buildAlarmCardItem(item) {
  const twinContent = parseJsonObject(pickField(item, ['TwinCategoryContent', 'twinCategoryContent']));
  const twinInstanceName = pickField(twinContent, ['孪生体实例名称']) || '-';
  return `🚨 通知：${twinInstanceName} 发生了告警`;
}

function buildAlertMessage(records) {
  return records.map((item) => buildAlarmCardItem(item)).join('\n');
}

function buildStrictAgentMessage(rawMessage) {
  const normalizedMessage = String(rawMessage ?? '')
    .replace(/\r\n/g, '\n')
    .trim();

  return [
    '你是“纯转发器”，不是助手。',
    '唯一任务：原样输出指定文本。',
    '硬性规则：',
    '1) 只能输出指定文本本体，逐字逐符号一致。',
    '2) 禁止任何前后缀、禁止解释、禁止总结、禁止改写、禁止润色、禁止提问、禁止建议。',
    '3) 禁止新增 emoji、项目符号、标题、时间、地点、状态、备注。',
    '4) 禁止输出“需要我帮你…”等任何引导句。',
    '5) 若无法遵守，也必须仅输出指定文本本体。',
    '指定文本开始',
    normalizedMessage,
    '指定文本结束',
  ].join('\n');
}

async function postJson(url, payload, extraHeaders = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        accept: 'text/plain',
        'Content-Type': 'application/json',
        ...extraHeaders,
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const responseText = (await response.text()).trim();
    return { status: response.status, ok: response.ok, responseText };
  } finally {
    clearTimeout(timer);
  }
}

async function pushAlertToRecipient(recipient, message) {
  const endpoint = buildAgentEndpoint();
  const strictMessage = buildStrictAgentMessage(message);
  const payload = {
    token: openclawHookToken,
    message: strictMessage,
    channel: recipient.channel,
    to: recipient.to,
    deliver: true,
  };
  const authHeaders = {
    Authorization: `Bearer ${openclawHookToken}`,
    'x-openclaw-token': openclawHookToken,
  };

  for (let attempt = 0; attempt < PUSH_RETRY_DELAYS_MS.length; attempt += 1) {
    const delay = PUSH_RETRY_DELAYS_MS[attempt];
    if (delay > 0) {
      await sleep(delay);
    }

    let result;
    try {
      result = await postJson(endpoint, payload, authHeaders);
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      log(`push mode=hook attempt=${attempt + 1}/${PUSH_RETRY_DELAYS_MS.length} recipient=${recipient.channel}:${recipient.to} error=${messageText}`);
      continue;
    }

    log(
      `push mode=hook attempt=${attempt + 1}/${PUSH_RETRY_DELAYS_MS.length} endpoint=${endpoint} recipient=${recipient.channel}:${recipient.to} ` +
        `status=${result.status} ok=${result.ok} body=${result.responseText}`
    );

    if (result.ok) {
      return { ok: true };
    }
  }

  return { ok: false };
}

if (!mqttPassword) {
  log('Missing required MQTT credentials.');
  cleanup();
  process.exit(1);
}

if (!mqttUrl.startsWith('mqtt://') && !mqttUrl.startsWith('mqtts://')) {
  log('Invalid MQTT_URL format. Expected mqtt:// or mqtts://');
  cleanup();
  process.exit(1);
}

if (!openclawHookBaseUrl.startsWith('http://') && !openclawHookBaseUrl.startsWith('https://')) {
  log('Invalid OPENCLAW_HOOK_BASE_URL format. Expected http:// or https://');
  cleanup();
  process.exit(1);
}

if (!openclawHookToken) {
  log('Missing required OPENCLAW_HOOK_TOKEN.');
  cleanup();
  process.exit(1);
}

if (configuredQos !== mqttQos) {
  log(`Invalid MQTT_QOS=${process.env.MQTT_QOS}, fallback to 1.`);
}

let recipients;
try {
  recipients = parseRecipients();
} catch (error) {
  const messageText = error instanceof Error ? error.message : String(error);
  log(`Invalid recipients config: ${messageText}`);
  cleanup();
  process.exit(1);
}

let consumerState = loadConsumerState();
let processingQueue = Promise.resolve();

const client = mqtt.connect(mqttUrl, {
  clientId: mqttClientId,
  username: mqttUsername,
  password: mqttPassword,
  reconnectPeriod: 5000,
});

client.on('connect', () => {
  log(`Connected to ${mqttUrl}`);
  client.subscribe(mqttTopic, { qos: mqttQos }, (error) => {
    if (error) {
      log(`Subscribe failed for ${mqttTopic}: ${error.message}`);
      return;
    }
    log(`Subscribed to ${mqttTopic} with qos=${mqttQos}`);
  });
});

client.on('reconnect', () => {
  log('Reconnecting to MQTT broker...');
});

client.on('error', (error) => {
  log(`MQTT error: ${error.message}`);
});

async function processMessage(topic, payloadBuffer) {
  const payloadText = payloadBuffer.toString('utf8');
  const parsedPayload = tryParseJson(payloadText);

  if (isDebugLogEnabled()) {
    log(`Received alarm message on ${topic}: ${payloadText}`);
  } else {
    log(`Received alarm message on ${topic} (${payloadBuffer.byteLength} bytes).`);
  }

  if (!hasAlarmData(parsedPayload, payloadText)) {
    log(`No alarm data recognized on topic=${topic}, skip actions.`);
    return;
  }

  const payloadObject = parsedPayload && typeof parsedPayload === 'object' ? parsedPayload : null;
  const extractedRecords = extractAlarmRecords(payloadObject);
  const matchedRecords = filterRecordsByLocation(extractedRecords, TARGET_BELONG_TO_LOCATION_ID);
  if (matchedRecords.length === 0) {
    log(`No records matched BelongToLocationID=${TARGET_BELONG_TO_LOCATION_ID} on topic=${topic}, skip actions.`);
    return;
  }

  const alertMessage = buildAlertMessage(matchedRecords);
  const payloadForState = { BelongToLocationID: TARGET_BELONG_TO_LOCATION_ID, Data: matchedRecords };
  const currentSignature = buildAlarmSignature(topic, payloadForState);
  const failedRecipients = [];
  const pushedRecipients = [];
  let stateChanged = false;

  for (const recipient of recipients) {
    const key = recipientKey(recipient);
    const lastSignature = consumerState.recipientSignatures[key];

    if (lastSignature === currentSignature) {
      log(`Alarm signature unchanged for recipient=${key}, skip push.`);
      continue;
    }

    const result = await pushAlertToRecipient(recipient, alertMessage);
    if (result.ok) {
      consumerState.recipientSignatures[key] = currentSignature;
      pushedRecipients.push(key);
      stateChanged = true;
    } else {
      failedRecipients.push(key);
    }
  }

  if (stateChanged) {
    saveConsumerState(consumerState);
  }

  if (pushedRecipients.length > 0) {
    log(`Alarm push completed for topic=${topic} recipients=${pushedRecipients.join(',')}`);
  } else if (failedRecipients.length === 0) {
    log(`Alarm push skipped for topic=${topic} (all recipients already deduped).`);
  }

  if (failedRecipients.length > 0) {
    log(`Alarm push failed for topic=${topic} recipients=${failedRecipients.join(',')}`);
  }
}

client.on('message', (topic, payloadBuffer) => {
  processingQueue = processingQueue
    .then(() => processMessage(topic, payloadBuffer))
    .catch((error) => {
      const message = error instanceof Error ? error.message : String(error);
      log(`Alarm processing error for topic=${topic}: ${message}`);
    });
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    log(`Received ${signal}, shutting down.`);
    cleanup();
    client.end(true, () => process.exit(0));
  });
}
