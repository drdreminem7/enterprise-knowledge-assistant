export type KnowledgeBase = {
  id: number;
  name: string;
  description: string | null;
};

export type DocumentRecord = {
  id: number;
  knowledge_base_id: number;
  filename: string;
  file_type: string;
  status: string;
  page_count: number | null;
};

export type ChatCitation = {
  document_id: number;
  document_name: string;
  chunk_id: number;
  chunk_index: number;
  snippet: string;
};

export type ChatResponse = {
  conversation_id: number;
  question: string;
  answer: string;
  sources: ChatCitation[];
};

export type ChatMessage = {
  message_id: number | null;
  role: "user" | "assistant";
  content: string;
  rewritten_query?: string | null;
  created_at: string | null;
};

export type ChatHistoryItem = {
  conversation_id: number;
  knowledge_base_id: number;
  question: string;
  answer_preview: string;
  created_at: string;
};

export type ChatDetail = {
  conversation_id: number;
  knowledge_base_id: number;
  question: string;
  answer: string;
  created_at: string;
  messages: ChatMessage[];
  sources: ChatCitation[];
};

export type StreamChunkEvent = {
  type: "chunk";
  delta: string;
};

export type StreamDoneEvent = {
  type: "done";
  conversation: ChatDetail;
};

export type StreamErrorEvent = {
  type: "error";
  detail: string;
};

export type AnalyticsResponse = {
  document_count: number;
  chunk_count: number;
  conversation_count: number;
  average_latency_ms: number | null;
  feedback_count: number;
  useful_feedback_ratio: number | null;
  top_questions: Array<{
    question: string;
    count: number;
  }>;
};

export type FeedbackResponse = {
  id: number;
  conversation_id: number;
  rating: string;
  comment: string | null;
  created_at: string;
};
