import type {
  AnalyticsResponse,
  ChatDetail,
  ChatHistoryItem,
  ChatResponse,
  DocumentRecord,
  FeedbackResponse,
  KnowledgeBase,
  StreamChunkEvent,
  StreamDoneEvent,
  StreamErrorEvent,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  return request("/knowledge-bases");
}

export function createKnowledgeBase(payload: {
  name: string;
  description: string;
}): Promise<KnowledgeBase> {
  return request("/knowledge-bases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function listDocuments(): Promise<DocumentRecord[]> {
  return request("/documents");
}

export function uploadDocument(knowledgeBaseId: number, file: File): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("knowledge_base_id", String(knowledgeBaseId));
  form.append("file", file);

  return request("/documents/upload", {
    method: "POST",
    body: form,
  });
}

export function sendChat(payload: {
  knowledge_base_id: number;
  question: string;
  conversation_id?: number;
  top_k: number;
}): Promise<ChatResponse> {
  return request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function streamChat(
  payload: {
    knowledge_base_id: number;
    question: string;
    conversation_id?: number;
    top_k: number;
  },
  handlers: {
    onChunk: (delta: string) => void;
  },
): Promise<ChatDetail> {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  if (!response.body) {
    throw new Error("Streaming is not available in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completedConversation: ChatDetail | null = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }

      const event = JSON.parse(line) as StreamChunkEvent | StreamDoneEvent | StreamErrorEvent;
      if (event.type === "chunk") {
        handlers.onChunk(event.delta);
        continue;
      }

      if (event.type === "error") {
        throw new Error(event.detail);
      }

      completedConversation = event.conversation;
    }

    if (done) {
      break;
    }
  }

  if (!completedConversation) {
    throw new Error("The assistant stream finished without a final response.");
  }

  return completedConversation;
}

export function listChatHistory(knowledgeBaseId?: number): Promise<ChatHistoryItem[]> {
  const params = new URLSearchParams();
  if (knowledgeBaseId !== undefined) {
    params.set("knowledge_base_id", String(knowledgeBaseId));
  }

  const query = params.toString();
  return request(`/chat/history${query ? `?${query}` : ""}`);
}

export function getConversation(conversationId: number): Promise<ChatDetail> {
  return request(`/chat/${conversationId}`);
}

export function deleteConversation(conversationId: number): Promise<void> {
  return request(`/chat/${conversationId}`, {
    method: "DELETE",
  });
}

export function submitFeedback(payload: {
  conversation_id: number;
  rating: "useful" | "not_useful";
  comment?: string;
}): Promise<FeedbackResponse> {
  return request("/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchAnalytics(): Promise<AnalyticsResponse> {
  return request("/analytics");
}
