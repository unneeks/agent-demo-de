import { hashMessage } from "../../../shared/utils.js";

const listeners = new Set();

const state = {
  conversationTitle: "Current chat",
  messages: [],
  analysisById: {},
  activeMessageId: null,
  tooltip: null,
  backendStatus: "idle"
};

export function getState() {
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function emit() {
  for (const listener of listeners) {
    listener(state);
  }
}

export function setConversationTitle(title) {
  state.conversationTitle = title;
  emit();
}

export function upsertMessages(messages) {
  state.messages = messages.map((message) => ({
    ...message,
    messageHash: message.messageHash || hashMessage(message.text)
  }));
  emit();
}

export function setAnalysis(messageId, analysis) {
  state.analysisById[messageId] = analysis;
  emit();
}

export function openAnalysisPane(messageId) {
  state.activeMessageId = messageId;
  emit();
}

export function closeAnalysisPane() {
  state.activeMessageId = null;
  emit();
}

export function showTooltip(payload) {
  state.tooltip = payload;
  emit();
}

export function hideTooltip() {
  state.tooltip = null;
  emit();
}

export function setBackendStatus(status) {
  state.backendStatus = status;
  emit();
}

export function getMessageViewModels() {
  return state.messages.map((message) => ({
    ...message,
    analysis: state.analysisById[message.id] || null
  }));
}
