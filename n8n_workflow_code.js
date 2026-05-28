import { workflow, node, trigger, newCredential } from '@n8n/workflow-sdk';

const API = 'http://localhost:8888';
const CHAT_ID = '8773271293';

// ─── Credencial Telegram ───────────────────────────────────────────────────
const telegramCred = newCredential({
  type: 'telegramApi',
  name: 'News Radar Telegram Bot',
  data: { accessToken: '8865256559:REDACTED_TG_TOKEN_OLD' },
});

// ─── FLUXO 1: Pipeline automático (a cada 2h) ─────────────────────────────

const schedule = trigger({
  type: 'n8n-nodes-base.scheduleTrigger',
  version: 1.3,
  config: {
    name: 'A cada 2 horas',
    parameters: {
      rule: { interval: [{ field: 'hours', hoursInterval: 2 }] },
    },
  },
});

const collect = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: '1. Coletar feeds',
    parameters: {
      method: 'POST',
      url: `${API}/pipeline/collect`,
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: { limit_per_feed: 30 },
      executeOnce: true,
    },
  },
});

const rank = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: '2. Calcular ranking',
    parameters: {
      method: 'POST',
      url: `${API}/pipeline/rank`,
      executeOnce: true,
    },
  },
});

const batchBrasil = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: '3a. Lotes Brasil',
    parameters: {
      method: 'POST',
      url: `${API}/pipeline/make-batches`,
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: { scope: 'brasil', top: 200, batch_size: 30, days_back: 3 },
      executeOnce: true,
    },
  },
});

const batchPiaui = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: '3b. Lotes Piaui',
    parameters: {
      method: 'POST',
      url: `${API}/pipeline/make-batches`,
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: { scope: 'piaui', top: 200, batch_size: 30, days_back: 3 },
      executeOnce: true,
    },
  },
});

const batchTeresina = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: '3c. Lotes Teresina',
    parameters: {
      method: 'POST',
      url: `${API}/pipeline/make-batches`,
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: { scope: 'teresina', top: 200, batch_size: 30, days_back: 3 },
      executeOnce: true,
    },
  },
});

const checkBatches = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: '4. Checar lotes pendentes',
    parameters: {
      method: 'GET',
      url: `${API}/batches?status=pending`,
      executeOnce: true,
    },
  },
});

const notifyBatches = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: '5. Notificar Telegram',
    credentials: { telegramApi: telegramCred },
    parameters: {
      resource: 'message',
      operation: 'sendMessage',
      chatId: CHAT_ID,
      text: `*News Radar* - Ciclo concluido!\n\nLotes de IA prontos para analise.\nAbra o dashboard para processar.`,
      additionalFields: { parse_mode: 'Markdown' },
      executeOnce: true,
    },
  },
});

const cleanup = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: '6. Limpeza',
    parameters: {
      method: 'POST',
      url: `${API}/pipeline/cleanup`,
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: { days: 30, expire_batches_hours: 48 },
      executeOnce: true,
    },
  },
});

// ─── FLUXO 2: Aprovação via Telegram ──────────────────────────────────────

const telegramTrigger = trigger({
  type: 'n8n-nodes-base.telegramTrigger',
  version: 1.1,
  config: {
    name: 'Aprovacao Telegram',
    credentials: { telegramApi: telegramCred },
    parameters: {
      updates: ['callback_query'],
    },
  },
});

const parseCallback = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Parsear callback',
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `
const cb = $input.first().json?.callback_query;
if (!cb || !cb.data) return [];
const [action, articleId] = (cb.data || '').split(':');
const status = action === 'approve' ? 'approved' : 'rejected';
return [{ json: {
  articleId,
  status,
  user: cb.from?.first_name || 'Editor',
  chatId: String(cb.message?.chat?.id || ''),
  messageId: String(cb.message?.message_id || ''),
  caption: cb.message?.caption || '',
  callbackQueryId: cb.id,
}}];
      `.trim(),
    },
  },
});

const updateStatus = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Atualizar status banco',
    parameters: {
      method: 'POST',
      url: `${API}/cards/update-status`,
      sendBody: true,
      contentType: 'json',
      specifyBody: 'json',
      jsonBody: {
        article_id: '={{ $json.articleId }}',
        status: '={{ $json.status }}',
      },
    },
  },
});

const answerCallback = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'Responder callback',
    credentials: { telegramApi: telegramCred },
    parameters: {
      resource: 'callback',
      operation: 'answerQuery',
      queryId: '={{ $("Parsear callback").first().json.callbackQueryId }}',
      additionalFields: {
        text: '={{ $("Parsear callback").first().json.status === "approved" ? "Aprovado!" : "Rejeitado." }}',
        showAlert: false,
      },
    },
  },
});

const editMessage = node({
  type: 'n8n-nodes-base.telegram',
  version: 1.2,
  config: {
    name: 'Editar mensagem',
    credentials: { telegramApi: telegramCred },
    parameters: {
      resource: 'message',
      operation: 'editMessageText',
      chatId: '={{ $("Parsear callback").first().json.chatId }}',
      messageId: '={{ $("Parsear callback").first().json.messageId }}',
      text: '={{ $("Parsear callback").first().json.status === "approved" ? "APROVADO" : "REJEITADO" }} por {{ $("Parsear callback").first().json.user }}',
      additionalFields: { parse_mode: 'Markdown' },
    },
  },
});

// ─── Composição ───────────────────────────────────────────────────────────

export default workflow('news-radar-v2', 'News Radar — Pipeline Completo')
  .add(schedule)
  .to(collect)
  .to(rank)
  .to(batchBrasil)
  .to(batchPiaui)
  .to(batchTeresina)
  .to(checkBatches)
  .to(notifyBatches)
  .to(cleanup)
  .add(telegramTrigger)
  .to(parseCallback)
  .to(updateStatus)
  .to(answerCallback)
  .to(editMessage);
