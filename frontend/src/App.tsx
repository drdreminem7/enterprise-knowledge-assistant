import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  createKnowledgeBase,
  deleteConversation,
  fetchAnalytics,
  getConversation,
  listChatHistory,
  listDocuments,
  listKnowledgeBases,
  streamChat,
  submitFeedback,
  uploadDocument,
} from "./lib/api";
import type {
  AnalyticsResponse,
  ChatDetail,
  ChatHistoryItem,
  ChatMessage,
  DocumentRecord,
  KnowledgeBase,
} from "./types";

const EMPTY_ANALYTICS: AnalyticsResponse = {
  document_count: 0,
  chunk_count: 0,
  conversation_count: 0,
  average_latency_ms: null,
  feedback_count: 0,
  useful_feedback_ratio: null,
  top_questions: [],
};

const STREAM_RENDER_INTERVAL_MS = 20;
const STREAM_RENDER_MIN_STEP = 2;
const STREAM_RENDER_MAX_STEP = 6;

export default function App() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsResponse>(EMPTY_ANALYTICS);
  const [conversationHistory, setConversationHistory] = useState<ChatHistoryItem[]>([]);
  const [activeConversation, setActiveConversation] = useState<ChatDetail | null>(null);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<number | null>(null);

  const [kbName, setKbName] = useState("");
  const [kbDescription, setKbDescription] = useState("");
  const [question, setQuestion] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [pendingQuestionAt, setPendingQuestionAt] = useState<string | null>(null);
  const [streamingAnswer, setStreamingAnswer] = useState<string | null>(null);
  const [historyFilter, setHistoryFilter] = useState("");

  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isCreatingKb, setIsCreatingKb] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [isSendingFeedback, setIsSendingFeedback] = useState<"useful" | "not_useful" | null>(null);
  const [deletingConversationId, setDeletingConversationId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const streamQueueRef = useRef("");
  const streamTimerRef = useRef<number | null>(null);
  const streamDrainResolverRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!selectedKnowledgeBaseId) {
      setConversationHistory([]);
      setActiveConversation(null);
      setPendingQuestionAt(null);
      setStreamingAnswer(null);
      return;
    }

    setPendingQuestion(null);
    setPendingQuestionAt(null);
    setActiveConversation(null);
    setStreamingAnswer(null);
    void loadConversationHistory(selectedKnowledgeBaseId);
  }, [selectedKnowledgeBaseId]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeConversation, pendingQuestion, streamingAnswer, isLoadingConversation]);

  useEffect(() => {
    return () => {
      if (streamTimerRef.current !== null) {
        window.clearInterval(streamTimerRef.current);
      }
      streamDrainResolverRef.current?.();
    };
  }, []);

  const selectedKnowledgeBase = useMemo(
    () => knowledgeBases.find((item) => item.id === selectedKnowledgeBaseId) ?? null,
    [knowledgeBases, selectedKnowledgeBaseId],
  );

  const filteredDocuments = useMemo(() => {
    if (!selectedKnowledgeBaseId) {
      return [];
    }
    return documents.filter((document) => document.knowledge_base_id === selectedKnowledgeBaseId);
  }, [documents, selectedKnowledgeBaseId]);

  const visibleConversationHistory = useMemo(() => {
    const query = historyFilter.trim().toLowerCase();
    if (!query) {
      return conversationHistory;
    }

    return conversationHistory.filter((conversation) => {
      return (
        conversation.question.toLowerCase().includes(query) ||
        conversation.answer_preview.toLowerCase().includes(query)
      );
    });
  }, [conversationHistory, historyFilter]);

  async function bootstrap() {
    setIsBootstrapping(true);
    setErrorMessage(null);
    try {
      const [kbData, documentData, analyticsData] = await Promise.all([
        listKnowledgeBases(),
        listDocuments(),
        fetchAnalytics(),
      ]);
      setKnowledgeBases(kbData);
      setDocuments(documentData);
      setAnalytics(analyticsData);
      setSelectedKnowledgeBaseId((current) => current ?? kbData[0]?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsBootstrapping(false);
    }
  }

  async function handleCreateKnowledgeBase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!kbName.trim()) {
      return;
    }

    setIsCreatingKb(true);
    setErrorMessage(null);
    try {
      const created = await createKnowledgeBase({
        name: kbName.trim(),
        description: kbDescription.trim(),
      });
      setKnowledgeBases((current) => [...current, created]);
      setSelectedKnowledgeBaseId(created.id);
      setKbName("");
      setKbDescription("");
      setBanner("Knowledge base created.");
      await Promise.all([refreshAnalytics(), refreshDocuments()]);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsCreatingKb(false);
    }
  }

  async function handleUploadDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedKnowledgeBaseId || !uploadFile) {
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);
    try {
      const uploaded = await uploadDocument(selectedKnowledgeBaseId, uploadFile);
      setDocuments((current) => [uploaded, ...current]);
      setUploadFile(null);
      const fileInput = event.currentTarget.querySelector('input[type="file"]') as HTMLInputElement | null;
      if (fileInput) {
        fileInput.value = "";
      }
      setBanner("Document uploaded and indexed.");
      await Promise.all([refreshDocuments(), refreshAnalytics()]);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsUploading(false);
    }
  }

  async function handleAskQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedKnowledgeBaseId || !question.trim()) {
      return;
    }

    const askedQuestion = question.trim();
    setIsAsking(true);
    setErrorMessage(null);
    setBanner(null);
    setPendingQuestion(askedQuestion);
    setPendingQuestionAt(new Date().toISOString());
    setStreamingAnswer("");
    resetStreamRenderer();
    setQuestion("");
    try {
      const conversation = await streamChat(
        {
          knowledge_base_id: selectedKnowledgeBaseId,
          question: askedQuestion,
          conversation_id: activeConversation?.conversation_id,
          top_k: 5,
        },
        {
          onChunk: (delta) => {
            enqueueStreamDelta(delta);
          },
        },
      );
      await waitForStreamDrain();
      setActiveConversation(conversation);
      setPendingQuestionAt(null);
      setStreamingAnswer(null);
      await loadConversationHistory(selectedKnowledgeBaseId, conversation.conversation_id);
      setBanner("Grounded answer generated.");
      await refreshAnalytics();
    } catch (error) {
      flushRemainingStream();
      setQuestion(askedQuestion);
      setPendingQuestionAt(null);
      setStreamingAnswer(null);
      setErrorMessage(getErrorMessage(error));
    } finally {
      setPendingQuestion(null);
      setIsAsking(false);
    }
  }

  async function handleFeedback(rating: "useful" | "not_useful") {
    if (!activeConversation) {
      return;
    }

    setIsSendingFeedback(rating);
    setErrorMessage(null);
    try {
      await submitFeedback({
        conversation_id: activeConversation.conversation_id,
        rating,
      });
      setBanner(rating === "useful" ? "Marked as useful." : "Marked as not useful.");
      await refreshAnalytics();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsSendingFeedback(null);
    }
  }

  async function handleSelectConversation(conversationId: number) {
    setIsLoadingConversation(true);
    setErrorMessage(null);
    setPendingQuestion(null);
    setPendingQuestionAt(null);
    setStreamingAnswer(null);
    if (activeConversation?.conversation_id !== conversationId) {
      setActiveConversation(null);
    }
    try {
      const conversation = await getConversation(conversationId);
      setActiveConversation(conversation);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsLoadingConversation(false);
    }
  }

  async function handleDeleteConversation(conversationId: number) {
    if (!window.confirm("Delete this saved chat from the demo history?")) {
      return;
    }

    setDeletingConversationId(conversationId);
    setErrorMessage(null);
    try {
      await deleteConversation(conversationId);
      const remaining = conversationHistory.filter(
        (conversation) => conversation.conversation_id !== conversationId,
      );
      setConversationHistory(remaining);
      if (activeConversation?.conversation_id === conversationId) {
        setActiveConversation(null);
      }
      if (selectedKnowledgeBaseId && remaining.length > 0 && activeConversation?.conversation_id === conversationId) {
        await handleSelectConversation(remaining[0].conversation_id);
      }
      setBanner("Chat deleted.");
      await refreshAnalytics();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setDeletingConversationId(null);
    }
  }

  function handleStartNewChat() {
    setActiveConversation(null);
    setPendingQuestion(null);
    setPendingQuestionAt(null);
    setStreamingAnswer(null);
    setQuestion("");
    setBanner("New chat ready.");
    resetStreamRenderer();
    window.requestAnimationFrame(() => {
      composerInputRef.current?.focus();
    });
  }

  function enqueueStreamDelta(delta: string) {
    streamQueueRef.current += delta;
    if (streamTimerRef.current !== null) {
      return;
    }

    streamTimerRef.current = window.setInterval(() => {
      if (!streamQueueRef.current) {
        if (streamTimerRef.current !== null) {
          window.clearInterval(streamTimerRef.current);
          streamTimerRef.current = null;
        }
        streamDrainResolverRef.current?.();
        streamDrainResolverRef.current = null;
        return;
      }

      const step = Math.min(
        STREAM_RENDER_MAX_STEP,
        Math.max(STREAM_RENDER_MIN_STEP, Math.ceil(streamQueueRef.current.length / 40)),
      );
      const nextChunk = streamQueueRef.current.slice(0, step);
      streamQueueRef.current = streamQueueRef.current.slice(step);
      setStreamingAnswer((current) => `${current ?? ""}${nextChunk}`);
    }, STREAM_RENDER_INTERVAL_MS);
  }

  function flushRemainingStream() {
    if (streamQueueRef.current) {
      const remaining = streamQueueRef.current;
      streamQueueRef.current = "";
      setStreamingAnswer((current) => `${current ?? ""}${remaining}`);
    }

    if (streamTimerRef.current !== null) {
      window.clearInterval(streamTimerRef.current);
      streamTimerRef.current = null;
    }

    streamDrainResolverRef.current?.();
    streamDrainResolverRef.current = null;
  }

  function resetStreamRenderer() {
    streamQueueRef.current = "";
    if (streamTimerRef.current !== null) {
      window.clearInterval(streamTimerRef.current);
      streamTimerRef.current = null;
    }
    streamDrainResolverRef.current = null;
  }

  function waitForStreamDrain() {
    if (!streamQueueRef.current && streamTimerRef.current === null) {
      return Promise.resolve();
    }

    return new Promise<void>((resolve) => {
      streamDrainResolverRef.current = resolve;
    });
  }

  async function refreshAnalytics() {
    try {
      const analyticsData = await fetchAnalytics();
      setAnalytics(analyticsData);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function refreshDocuments() {
    try {
      const documentData = await listDocuments();
      setDocuments(documentData);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function loadConversationHistory(
    knowledgeBaseId: number,
    preferredConversationId?: number,
  ) {
    try {
      const history = await listChatHistory(knowledgeBaseId);
      setConversationHistory(history);

      const conversationToOpen =
        preferredConversationId ??
        (activeConversation?.knowledge_base_id === knowledgeBaseId
          ? activeConversation.conversation_id
          : history[0]?.conversation_id);

      if (!conversationToOpen) {
        setActiveConversation(null);
        return;
      }

      if (preferredConversationId || conversationToOpen !== activeConversation?.conversation_id) {
        await handleSelectConversation(conversationToOpen);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  const renderedMessages = buildRenderedMessages(
    activeConversation?.messages ?? [],
    pendingQuestion,
    pendingQuestionAt,
    streamingAnswer,
  );
  const activeConversationId = activeConversation?.conversation_id ?? null;

  return (
    <div className="app-shell">
      <div className="ambient-layer" />

      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-badge">Enterprise RAG Demo</div>
          <div>
            <h1>Knowledge Chat</h1>
            <p>ChatGPT-style shell with grounded enterprise retrieval underneath.</p>
          </div>
        </div>

        <button
          className="new-chat-button"
          type="button"
          onClick={handleStartNewChat}
          disabled={!selectedKnowledgeBaseId || isAsking}
        >
          New chat
        </button>

        <label className="history-search">
          <span>Search chats</span>
          <input
            value={historyFilter}
            onChange={(event) => setHistoryFilter(event.target.value)}
            placeholder="Search chat history..."
          />
        </label>

        <section className="sidebar-block">
          <div className="sidebar-block-heading">
            <span>Knowledge bases</span>
            <strong>{knowledgeBases.length}</strong>
          </div>

          <div className="sidebar-kb-list">
            {knowledgeBases.length === 0 ? (
              <EmptyState
                title="No knowledge bases"
                message="Create one below to start a grounded chat workspace."
              />
            ) : (
              knowledgeBases.map((item) => (
                <button
                  key={item.id}
                  className={`sidebar-kb-item ${item.id === selectedKnowledgeBaseId ? "selected" : ""}`}
                  onClick={() => setSelectedKnowledgeBaseId(item.id)}
                  type="button"
                >
                  <strong>{item.name}</strong>
                  <span>{item.id === selectedKnowledgeBaseId ? "Active" : "Switch"}</span>
                </button>
              ))
            )}
          </div>
        </section>

        <details className="sidebar-disclosure" open>
          <summary>Create knowledge base</summary>
          <form className="sidebar-form" onSubmit={handleCreateKnowledgeBase}>
            <label>
              <span>Name</span>
              <input
                value={kbName}
                onChange={(event) => setKbName(event.target.value)}
                placeholder="HR Demo"
              />
            </label>
            <label>
              <span>Description</span>
              <textarea
                value={kbDescription}
                onChange={(event) => setKbDescription(event.target.value)}
                placeholder="Policy and process knowledge base"
                rows={3}
              />
            </label>
            <button className="primary-button" type="submit" disabled={isCreatingKb}>
              {isCreatingKb ? "Creating..." : "Create"}
            </button>
          </form>
        </details>

        <details className="sidebar-disclosure" open>
          <summary>Documents</summary>
          <form className="sidebar-form" onSubmit={handleUploadDocument}>
            <label>
              <span>Upload file</span>
              <input
                type="file"
                accept=".txt,.pdf,.docx"
                onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                disabled={!selectedKnowledgeBaseId}
              />
            </label>
            <button
              className="primary-button"
              type="submit"
              disabled={!selectedKnowledgeBaseId || !uploadFile || isUploading}
            >
              {isUploading ? "Uploading..." : "Upload and index"}
            </button>
          </form>

          <div className="sidebar-document-list">
            {filteredDocuments.length === 0 ? (
              <EmptyState
                title="No indexed documents"
                message="Upload TXT, PDF, or DOCX files to power answers."
              />
            ) : (
              filteredDocuments.map((document) => (
                <article key={document.id} className="sidebar-document-item">
                  <div>
                    <strong>{document.filename}</strong>
                    <p>
                      {document.file_type.toUpperCase()} · {document.page_count ?? "N/A"} pages
                    </p>
                  </div>
                  <span className={`status-pill status-${document.status}`}>{document.status}</span>
                </article>
              ))
            )}
          </div>
        </details>

        <section className="sidebar-block sidebar-history">
          <div className="sidebar-block-heading">
            <span>Chats</span>
            <strong>{visibleConversationHistory.length}</strong>
          </div>

          {visibleConversationHistory.length === 0 ? (
            <EmptyState
              title="No chats found"
              message="Start a conversation or adjust your search."
            />
          ) : (
            <div className="sidebar-history-list">
              {visibleConversationHistory.map((conversation) => (
                <article
                  key={conversation.conversation_id}
                  className={`sidebar-history-item ${
                    conversation.conversation_id === activeConversationId ? "selected" : ""
                  }`}
                >
                  <button
                    type="button"
                    className="sidebar-history-main"
                    onClick={() => void handleSelectConversation(conversation.conversation_id)}
                    disabled={isAsking || isLoadingConversation}
                  >
                    <strong>{conversation.question}</strong>
                    <p>{conversation.answer_preview}</p>
                    <span>{formatTimestamp(conversation.created_at)}</span>
                  </button>
                  <button
                    type="button"
                    className="sidebar-history-delete"
                    onClick={() => void handleDeleteConversation(conversation.conversation_id)}
                    disabled={isAsking || deletingConversationId === conversation.conversation_id}
                    aria-label={`Delete conversation ${conversation.question}`}
                  >
                    {deletingConversationId === conversation.conversation_id ? "..." : "Delete"}
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>

        <footer className="sidebar-footer">
          <MetricCard label="Docs" value={String(analytics.document_count)} />
          <MetricCard label="Chunks" value={String(analytics.chunk_count)} />
          <MetricCard label="Chats" value={String(analytics.conversation_count)} />
        </footer>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div className="workspace-header-copy">
            <div className="eyebrow">Grounded Assistant</div>
            <h2>{selectedKnowledgeBase?.name ?? "Select a knowledge base to begin"}</h2>
            <p>
              {selectedKnowledgeBase
                ? "Ask naturally. We keep the chat flow continuous, but still retrieve from your indexed knowledge."
                : "Activate a knowledge base from the sidebar to start chatting."}
            </p>
          </div>
          <div className="workspace-header-meta">
            <span>{filteredDocuments.length} indexed docs</span>
            <span>{activeConversation?.sources.length ?? 0} latest sources</span>
          </div>
        </header>

        {(banner || errorMessage) && (
          <div className={`message-bar ${errorMessage ? "error" : "success"}`}>
            <span>{errorMessage ?? banner}</span>
          </div>
        )}

        <section className="workspace-thread">
          <div className="thread-scroll" aria-live="polite">
            {renderedMessages.length === 0 && !isLoadingConversation ? (
              <div className="welcome-state">
                <div className="welcome-copy">
                  <div className="eyebrow">Chat Workspace</div>
                  <h3>{isBootstrapping ? "Loading workspace..." : "Where should we begin?"}</h3>
                  <p>
                    Ask a direct question, or use a recurring one below to demo retrieval, follow-ups, and sources.
                  </p>
                </div>

                {analytics.top_questions.length > 0 && (
                  <div className="suggestion-grid">
                    {analytics.top_questions.map((item) => (
                      <button
                        key={item.question}
                        type="button"
                        className="suggestion-chip"
                        onClick={() => setQuestion(item.question)}
                      >
                        {item.question}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="thread-column">
                {renderedMessages.map((message, index) => (
                  <MessageBubble
                    key={`${message.message_id ?? "pending"}-${index}`}
                    role={message.role}
                    title={message.role === "user" ? "You" : "Assistant"}
                    body={message.content}
                    rewrittenQuery={message.rewritten_query}
                    timestamp={message.created_at}
                    isThinking={
                      message.role === "assistant" &&
                      (isAsking || isLoadingConversation) &&
                      !message.content
                    }
                  />
                ))}
              </div>
            )}

            {activeConversation && activeConversation.sources.length > 0 && (
              <section className="source-drawer">
                <div className="source-drawer-heading">
                  <strong>Latest retrieved sources</strong>
                  <span>{activeConversation.sources.length}</span>
                </div>
                <div className="source-drawer-list">
                  {activeConversation.sources.map((source) => (
                    <article key={source.chunk_id} className="source-drawer-card">
                      <div className="source-topline">
                        <strong>{source.document_name}</strong>
                        <span>Chunk {source.chunk_index}</span>
                      </div>
                      <p>{source.snippet}</p>
                    </article>
                  ))}
                </div>
              </section>
            )}

            {activeConversation && (
              <div className="feedback-row feedback-inline">
                <span>Was the latest answer useful?</span>
                <div className="feedback-actions">
                  <button
                    type="button"
                    className="ghost-button"
                    disabled={isSendingFeedback !== null}
                    onClick={() => void handleFeedback("useful")}
                  >
                    {isSendingFeedback === "useful" ? "Saving..." : "Useful"}
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    disabled={isSendingFeedback !== null}
                    onClick={() => void handleFeedback("not_useful")}
                  >
                    {isSendingFeedback === "not_useful" ? "Saving..." : "Not useful"}
                  </button>
                </div>
              </div>
            )}

            <div ref={threadEndRef} />
          </div>

          <form className="composer-dock" onSubmit={handleAskQuestion}>
            <div className="composer-shell">
              <textarea
                ref={composerInputRef}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Message your knowledge base..."
                rows={3}
                disabled={!selectedKnowledgeBaseId}
              />
              <div className="composer-footer">
                <div className="composer-copy">
                  {selectedKnowledgeBase
                    ? "Multi-turn chat stays in the same conversation until you start a new one."
                    : "Choose a knowledge base from the sidebar to unlock grounded chat."}
                </div>
                <button
                  className="primary-button"
                  type="submit"
                  disabled={!selectedKnowledgeBaseId || !question.trim() || isAsking}
                >
                  {isAsking ? "Thinking..." : "Send"}
                </button>
              </div>
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  );
}

function buildRenderedMessages(
  baseMessages: ChatMessage[],
  pendingQuestion: string | null,
  pendingQuestionAt: string | null,
  streamingAnswer: string | null,
): ChatMessage[] {
  const messages = [...baseMessages];

  if (pendingQuestion) {
    messages.push({
      message_id: null,
      role: "user",
      content: pendingQuestion,
      rewritten_query: null,
      created_at: pendingQuestionAt,
    });
  }

  if (streamingAnswer !== null) {
    messages.push({
      message_id: null,
      role: "assistant",
      content: streamingAnswer,
      rewritten_query: null,
      created_at: null,
    });
  }

  return messages;
}

function MessageBubble({
  role,
  title,
  body,
  rewrittenQuery,
  timestamp,
  isThinking = false,
}: {
  role: "user" | "assistant";
  title: string;
  body: string | null;
  rewrittenQuery?: string | null;
  timestamp: string | null;
  isThinking?: boolean;
}) {
  return (
    <article className={`message-row ${role}`}>
      <div className={`message-bubble ${role}`}>
        <div className="message-meta">
          <strong>{title}</strong>
          {timestamp && <span>{formatTimestamp(timestamp)}</span>}
        </div>
        {isThinking && !body ? (
          <div className="thinking-indicator" aria-label="Assistant is thinking">
            <span />
            <span />
            <span />
          </div>
        ) : (
          <>
            <p>{body}</p>
            {role === "user" && rewrittenQuery && rewrittenQuery !== body && (
              <div className="message-query-trace">
                <span>Searched as</span>
                <strong>{rewrittenQuery}</strong>
              </div>
            )}
          </>
        )}
      </div>
    </article>
  );
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    try {
      const parsed = JSON.parse(error.message) as { detail?: string };
      if (parsed.detail) {
        return parsed.detail;
      }
    } catch {
      return error.message;
    }
  }
  return "Something went wrong.";
}
