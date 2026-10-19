import { useCallback, useRef, useState } from "react";
import { ApiError, sendChat, type ApiErrorKind } from "../api/client";
import type { ChatResult, ChatTurn } from "../api/types";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: ChatResult;
  error?: { message: string; kind: string };
  /** For failed assistant turns: the question to resend on retry. */
  question?: string;
}

const HISTORY_LIMIT = 12;
let counter = 0;
const nextId = () => `m${Date.now().toString(36)}${(counter++).toString(36)}`;

/** Conversation history sent to the API: successful turns only, most recent last. */
export function historyFrom(messages: Message[]): ChatTurn[] {
  return messages
    .filter((m) => !m.error && m.content.trim())
    .map((m) => ({ role: m.role, content: m.content }))
    .slice(-HISTORY_LIMIT);
}

/** Request lifecycle, reported as it really happens (the robot's moments follow it). */
export type ChatStatusEvent =
  | { type: "retrieving" }
  | { type: "answered"; result: ChatResult }
  | { type: "failed"; kind: ApiErrorKind };

export function useChat(onEvent?: (event: ChatStatusEvent) => void) {
  const [messages, setMessages] = useState<Message[]>([]);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const [loading, setLoading] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;

  const ask = useCallback(async (question: string, history: ChatTurn[]) => {
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    setLoading(true);
    onEventRef.current?.({ type: "retrieving" });
    try {
      const result = await sendChat(question, history, ctrl.signal);
      if (ctrl.signal.aborted) return;
      setMessages((prev) => [...prev, { id: nextId(), role: "assistant", content: result.answer, result }]);
      onEventRef.current?.({ type: "answered", result });
    } catch (err) {
      if (ctrl.signal.aborted) return;
      const error: { message: string; kind: ApiErrorKind } =
        err instanceof ApiError ? { message: err.message, kind: err.kind } : { message: "Something went wrong. Please try again.", kind: "server" };
      setMessages((prev) => [...prev, { id: nextId(), role: "assistant", content: "", error, question }]);
      onEventRef.current?.({ type: "failed", kind: error.kind });
    } finally {
      if (controller.current === ctrl) {
        controller.current = null;
        setLoading(false);
      }
    }
  }, []);

  const send = useCallback(
    (text: string) => {
      const question = text.trim();
      if (!question || controller.current) return;
      const history = historyFrom(messagesRef.current);
      setMessages((prev) => [...prev, { id: nextId(), role: "user", content: question }]);
      void ask(question, history);
    },
    [ask],
  );

  const retry = useCallback(
    (errorId: string) => {
      const current = messagesRef.current;
      const failed = current.find((m) => m.id === errorId);
      if (!failed?.question || controller.current) return;
      const remaining = current.filter((m) => m.id !== errorId);
      setMessages(remaining);
      // history excludes the question itself, which is the last user turn
      const history = historyFrom(remaining).slice(0, -1);
      void ask(failed.question, history);
    },
    [ask],
  );

  const reset = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setLoading(false);
    setMessages([]);
  }, []);

  return { messages, loading, send, retry, reset };
}
