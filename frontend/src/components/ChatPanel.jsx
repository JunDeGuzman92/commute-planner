"use client";

import { useState, useRef, useEffect } from "react";
import { API_URL } from "../lib/config";

const SUGGESTIONS = [
  "Cheapest way there?",
  "When should I leave?",
  "Is this route reliable?",
  "Plan my week",
  "Is the monthly pass worth it?",
  "What if it rains?",
];

export default function ChatPanel({ planParams }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hi! Ask me anything about this trip — cost, timing, reliability, weekly planning, or long-distance options.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text) => {
    const msg = (text || input).trim();
    if (!msg || !planParams) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: msg }]);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...planParams, message: msg }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setMessages((m) => [...m, {
        role: "assistant",
        text: data.reply,
        intent: data.intent,
      }]);
    } catch {
      setMessages((m) => [...m, {
        role: "assistant",
        text: "Something went wrong reaching the planner. Try again.",
      }]);
    } finally {
      setLoading(false);
    }
  };

  if (!planParams) {
    return (
      <div className="text-xs text-gray-500 p-2">
          Set an origin and destination first, then ask me anything about the
          trip.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-2 mb-2 max-h-80">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`text-xs rounded-lg px-3 py-2 ${
              m.role === "user"
                ? "bg-blue-600 text-white ml-8"
                : "bg-gray-100 text-gray-800 mr-4"
            }`}
          >
            {m.text}
          </div>
        ))}
        {loading && (
          <div className="text-xs text-gray-400 italic mr-4">Thinking...</div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex flex-wrap gap-1 mb-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => send(s)}
            disabled={loading}
            className="text-[10px] px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded-full text-gray-600"
          >
            {s}
          </button>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="flex gap-1"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this trip..."
          className="flex-1 text-xs border rounded px-2 py-1.5"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-blue-600 text-white text-xs px-3 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
